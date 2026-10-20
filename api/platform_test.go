package main

import (
	"encoding/json"
	"net/http"
	"strings"
	"sync"
	"testing"
	"time"
)

func testCatalog() PlatformCatalog {
	mk := func(id, role, model string, in, out int64) PlatformModel {
		return PlatformModel{ID: id, Label: model, Role: role, Enabled: true, Channel: Channel{BaseURL: "https://models.example.org/v1", APIKey: "secret-platform-credential", Model: model, MaxTokens: 24000, Protocol: "chat_completions"}, Price: Rate{Model: model, Input: in, Output: out, Cached: in / 10, MaxInput: 1000000}}
	}
	return PlatformCatalog{Models: []PlatformModel{mk("platform-text-default", "text", "generation", 2000000, 8000000), mk("platform-vision-default", "vision", "review", 800000, 2700000)}, DefaultText: "platform-text-default", DefaultVision: "platform-vision-default", Revision: 1, RechargeHelp: "联系管理员确认收款后入账"}
}
func adminCookie(t *testing.T, store *Store, s *Server) *http.Cookie {
	u, c := registered(t, s, "managed-admin")
	if _, err := store.DB.Exec("UPDATE users SET role='admin' WHERE id=?", u.ID); err != nil {
		t.Fatal(err)
	}
	return c
}
func TestPlatformSelectionSecretsAndPersonalPersistence(t *testing.T) {
	store, s := fixture(t)
	s.Billing.Enabled = true
	c := testCatalog()
	if err := store.saveCatalog(c, store.adminID()); err != nil {
		t.Fatal(err)
	}
	u, cookie := registered(t, s, "new-creator")
	w := call(t, s, "GET", "/api/config", nil, cookie, "")
	var config PersonalConfig
	json.Unmarshal(w.Body.Bytes(), &config)
	if w.Code != 200 || !config.UsePlatform || !config.TextReady || config.Saved || strings.Contains(w.Body.String(), "secret-platform") {
		t.Fatal("unsafe or unavailable default", w.Code, w.Body.String())
	}
	w = call(t, s, "GET", "/api/billing", nil, cookie, "")
	if strings.Contains(w.Body.String(), "models.example.org") || strings.Contains(w.Body.String(), "secret-platform") {
		t.Fatal("platform endpoint or key exposed")
	}
	frozen, err := s.effective(config)
	if err != nil || frozen.Text.Model != "generation" || len(frozen.PlatformPrices) != 2 {
		t.Fatal(frozen, err)
	}
	config.PlatformText = "arbitrary-billable-model"
	if _, err = s.effective(config); err == nil {
		t.Fatal("unknown selection used platform credential")
	}
	personal := defaultConfig()
	personal.Text = Channel{BaseURL: "https://personal.example.org/v1", Model: "mine", APIKey: "my-own-key", Protocol: "chat_completions"}
	store.saveConfig(u.ID, personal)
	w = call(t, s, "GET", "/api/config", nil, cookie, "")
	json.Unmarshal(w.Body.Bytes(), &config)
	if config.UsePlatform || config.Text.Model != "mine" || !config.Saved || strings.Contains(w.Body.String(), "my-own-key") {
		t.Fatal("personal settings overwritten or exposed")
	}
	// An explicit BYOK choice with no key must remain unconfigured, never silently switch to paid.
	store.saveConfig(u.ID, defaultConfig())
	w = call(t, s, "GET", "/api/config", nil, cookie, "")
	json.Unmarshal(w.Body.Bytes(), &config)
	if config.UsePlatform || config.TextReady || !config.Saved {
		t.Fatal("explicit BYOK choice overwritten")
	}
	var raw []byte
	store.DB.QueryRow("SELECT ciphertext FROM platform_settings WHERE id=1").Scan(&raw)
	if strings.Contains(string(raw), "secret-platform") {
		t.Fatal("unencrypted platform secret")
	}
	for _, path := range []string{"/api/admin/platform", "/api/admin/usage"} {
		if w = call(t, s, "GET", path, nil, cookie, ""); w.Code != 403 {
			t.Fatal("admin route exposed", path)
		}
	}
}
func TestPrepayConcurrentReservationsAndBalanceReduction(t *testing.T) {
	store, s := fixture(t)
	s.Billing.Enabled = true
	store.saveCatalog(testCatalog(), store.adminID())
	u, _ := registered(t, s, "paid-creator")
	c := defaultConfig()
	c.UsePlatform = true
	c, _ = s.effective(c)
	store.saveTaskConfig(u.ID, "paid-job", c)
	d := meterRequest{ID: randomID(16), UserID: u.ID, JobID: "paid-job", Role: "text", Model: "generation", MaxOutput: 24000, InputBound: 10000}
	if _, err := s.Billing.authorize(d); err == nil {
		t.Fatal("free platform call authorized")
	}
	store.credit(store.adminID(), u.ID, 499, "partial payment", "first-payment-499")
	if _, err := s.Billing.authorize(d); err == nil {
		t.Fatal("minimum deposit bypassed")
	}
	store.credit(store.adminID(), u.ID, 1, "rest of payment", "second-payment-1")
	if _, err := store.credit(store.adminID(), u.ID, 100, "reserved prefix", "usage-manual-credit"); err == nil {
		t.Fatal("manual adjustment impersonated system usage")
	}
	// 22 cents per reservation: 22 concurrent admissions fit, the rest must fail atomically.
	var wg sync.WaitGroup
	var mu sync.Mutex
	success := []meterRequest{}
	for i := 0; i < 30; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			call := d
			call.ID = randomID(16)
			if _, err := s.Billing.authorize(call); err == nil {
				mu.Lock()
				success = append(success, call)
				mu.Unlock()
			}
		}()
	}
	wg.Wait()
	if len(success) != 22 {
		t.Fatal("unexpected concurrent admissions", len(success))
	}
	if _, err := store.credit(store.adminID(), u.ID, -100, "refund blocked by reservations", "refund-protected-1"); err == nil {
		t.Fatal("reserved credit was removed")
	}
	for _, call := range success {
		call.Metered = true
		call.Input = 1000
		call.Output = 100
		call.Cached = 500
		call.ResponseID = "upstream-safe-id"
		call.DurationMS = 300
		call.Usage = json.RawMessage(`{"prompt_tokens":1000,"secret":"never store this"}`)
		if _, err := s.Billing.settle(call); err != nil {
			t.Fatal(err)
		}
		if _, err := s.Billing.settle(call); err != nil {
			t.Fatal(err)
		}
	}
	after, _ := store.user(u.ID)
	if after.Balance != 495 {
		t.Fatal("cumulative rounding or duplicate settlement", after.Balance)
	}
	e, err := store.credit(store.adminID(), u.ID, -100, "refund after completion", "refund-after-completion")
	if err != nil || e.Balance != 395 {
		t.Fatal(e, err)
	}
	same, err := store.credit(store.adminID(), u.ID, -100, "refund after completion", "refund-after-completion")
	if err != nil || same.ID != e.ID {
		t.Fatal("adjustment not idempotent")
	}
	var audit string
	store.DB.QueryRow("SELECT usage FROM billing_calls LIMIT 1").Scan(&audit)
	if strings.Contains(audit, "never store") {
		t.Fatal("unbounded provider metadata stored")
	}
}
func TestUsageOwnershipBYOKAndReconciliation(t *testing.T) {
	store, s := fixture(t)
	u, cookie := registered(t, s, "own-key")
	other, otherCookie := registered(t, s, "another-user")
	_ = other
	c := defaultConfig()
	c.Text.Model = "byok-model"
	store.saveTaskConfig(u.ID, "own-job", c)
	d := meterRequest{ID: randomID(16), UserID: u.ID, JobID: "own-job", Role: "text", Model: "byok-model", InputBound: 1000, MaxOutput: 1000}
	if _, err := s.Billing.authorize(d); err != nil {
		t.Fatal(err)
	}
	d.Metered = true
	d.Input = 200
	d.Output = 300
	d.Usage = json.RawMessage(`{}`)
	if _, err := s.Billing.settle(d); err != nil {
		t.Fatal(err)
	}
	after, _ := store.user(u.ID)
	if after.Balance != 0 {
		t.Fatal("BYOK charged")
	}
	w := call(t, s, "GET", "/api/usage", nil, cookie, "")
	if w.Code != 200 || !strings.Contains(w.Body.String(), "byok-model") || !strings.Contains(w.Body.String(), `"input_tokens":200`) {
		t.Fatal(w.Code, w.Body.String())
	}
	w = call(t, s, "GET", "/api/usage?user_id="+u.ID, nil, otherCookie, "")
	if w.Code != 200 || strings.Contains(w.Body.String(), "byok-model") {
		t.Fatal("cross-account usage access")
	}
	admin := adminCookie(t, store, s)
	w = call(t, s, "GET", "/api/admin/usage?user_id="+u.ID, nil, admin, "")
	if w.Code != 200 || !strings.Contains(w.Body.String(), "byok-model") {
		t.Fatal("admin usage unavailable")
	}
	d.ID = randomID(16)
	d.Metered = false
	s.Billing.authorize(d)
	s.Billing.settle(d)
	w = call(t, s, "POST", "/api/admin/usage/"+d.ID+"/reconcile", map[string]any{"input_tokens": 10, "output_tokens": 20, "cached_input_tokens": 0, "note": "checked upstream receipt 123"}, admin, "")
	if w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	var n int
	store.DB.QueryRow("SELECT count(*) FROM admin_audit WHERE action='usage.reconcile'").Scan(&n)
	if n != 1 {
		t.Fatal("missing reconciliation audit")
	}
	w = call(t, s, "POST", "/api/admin/usage/"+d.ID+"/reconcile", map[string]any{"input_tokens": 10, "output_tokens": 20, "note": "checked upstream receipt 123"}, admin, "")
	if w.Code != 200 {
		t.Fatal("repeated settlement failed")
	}
	store.DB.QueryRow("SELECT count(*) FROM admin_audit WHERE action='usage.reconcile'").Scan(&n)
	if n != 1 {
		t.Fatal("duplicate audit settlement")
	}
	d.ID = randomID(16)
	s.Billing.authorize(d)
	d.Rejected = true
	s.Billing.settle(d)
	var status string
	store.DB.QueryRow("SELECT status FROM billing_calls WHERE id=?", d.ID).Scan(&status)
	if status != "rejected" {
		t.Fatal("rejected request retained hold")
	}
}
func TestManagedUserAndPriceSnapshots(t *testing.T) {
	store, s := fixture(t)
	s.Billing.Enabled = true
	admin := adminCookie(t, store, s)
	w := call(t, s, "POST", "/api/admin/users", map[string]string{"username": "new-managed", "display_name": "managed", "password": "secure-password-2026"}, admin, "")
	if w.Code != 201 {
		t.Fatal(w.Code, w.Body.String())
	}
	var u User
	json.Unmarshal(w.Body.Bytes(), &u)
	if u.Role != "user" || u.Balance != 0 {
		t.Fatal("creation granted privileges or money")
	}
	catalog := testCatalog()
	store.saveCatalog(catalog, store.adminID())
	cfg := defaultConfig()
	cfg.UsePlatform = true
	cfg, _ = s.effective(cfg)
	store.saveTaskConfig(u.ID, "fixed-price-job", cfg)
	store.credit(store.adminID(), u.ID, 500, "prepayment receipt", "snapshot-credit-01")
	catalog.Models[0].Price.Input = 999000000
	catalog.Revision = 2
	store.saveCatalog(catalog, store.adminID())
	d := meterRequest{ID: randomID(16), UserID: u.ID, JobID: "fixed-price-job", Model: "generation", Role: "text", MaxOutput: 1000, InputBound: 1000}
	if _, err := s.Billing.authorize(d); err != nil {
		t.Fatal(err)
	}
	d.Metered = true
	d.Input = 1000
	d.Output = 1000
	d.Usage = json.RawMessage(`{}`)
	result, err := s.Billing.settle(d)
	if err != nil || result["cost_micro"].(int64) != 10000 {
		t.Fatal("task price changed", result, err)
	}
	w = call(t, s, "GET", "/api/usage?from=invalid", nil, admin, "")
	if w.Code != 422 {
		t.Fatal("invalid date accepted")
	}
	w = call(t, s, "GET", "/api/admin/usage?from="+time.Now().UTC().Format("2006-01-02"), nil, admin, "")
	if w.Code != 200 {
		t.Fatal(w.Body.String())
	}
}

func TestPartialCatalogCanBeSavedWithoutOpeningPlatform(t *testing.T) {
	store, s := fixture(t)
	s.Billing.Enabled = true
	cookie := adminCookie(t, store, s)
	c := PlatformCatalog{Models: []PlatformModel{{ID: "draft-platform-model", Role: "text", Label: "draft", Channel: Channel{Protocol: "chat_completions", MaxTokens: 24000}, Price: Rate{Input: 2000000, Output: 8000000, MaxInput: 1000000}}}}
	w := call(t, s, "PUT", "/api/admin/platform", c, cookie, "")
	if w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	saved, err := store.catalog()
	if err != nil || saved.Revision != 1 || s.platformAvailable(saved) {
		t.Fatal("draft settings activated platform")
	}
	w = call(t, s, "PUT", "/api/admin/platform", c, cookie, "")
	if w.Code != 409 {
		t.Fatal("stale settings overwrote catalog")
	}
}
