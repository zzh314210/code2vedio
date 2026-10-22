package main

import (
	"encoding/json"
	"strings"
	"testing"
	"time"
)

func TestBillingReservationAndActualUsage(t *testing.T) {
	store, s := fixture(t)
	u, _ := registered(t, s, "billed")
	store.credit(store.adminID(), u.ID, 10000, "test deposit", "billing-deposit-00001")
	cfg := defaultConfig()
	cfg.UsePlatform = true
	cfg.Text.Model = "test-model"
	cfg.Text.BaseURL = "https://model.example.org/v1"
	store.saveTaskConfig(u.ID, "job-billing", cfg)
	b := s.Billing
	b.Enabled = true
	b.Prices = PriceBook{EndpointSuffix: ".example.org", Rates: []Rate{{Model: "test-model", Input: 20000000, Output: 100000000, Cached: 2000000, MaxInput: 1000000}}}
	d := meterRequest{ID: strings.Repeat("a", 32), UserID: u.ID, JobID: "job-billing", Model: "test-model", Role: "text", MaxOutput: 12000}
	d.Reasoning = map[string]any{"provider": "deepseek", "enabled": true, "requested_effort": "max", "effective_effort": "max", "api_key": "do-not-store"}
	result, err := b.authorize(d)
	if err != nil || result["reserved_cents"].(int64) != 2120 {
		t.Fatal(result, err)
	}
	// Repeated authorization must not create another hold.
	if _, err = b.authorize(d); err != nil {
		t.Fatal(err)
	}
	d.Reasoning = nil // A later reconciliation must preserve the authorized policy.
	d.Metered = true
	d.Input = 1000
	d.Cached = 500
	d.Output = 100
	d.Usage = json.RawMessage(`{"prompt_tokens":1000,"completion_tokens":100}`)
	result, err = b.settle(d)
	if err != nil || result["cost_micro"].(int64) != 21000 || result["charged_cents"].(int64) != 3 {
		t.Fatal(result, err)
	}
	result, err = b.settle(d)
	if err != nil || result["charged_cents"].(int64) != 3 {
		t.Fatal("settlement not idempotent", result, err)
	}
	var audit string
	store.DB.QueryRow("SELECT usage FROM billing_calls WHERE id=?", d.ID).Scan(&audit)
	if !strings.Contains(audit, `"effective_effort":"max"`) || strings.Contains(audit, "do-not-store") {
		t.Fatal("reasoning policy lost or secret persisted", audit)
	}
	actual, _ := store.user(u.ID)
	if actual.Balance != 9997 {
		t.Fatal(actual.Balance)
	}
	d.ID = strings.Repeat("b", 32)
	b.authorize(d)
	d.Input = 1
	d.Cached = 0
	d.Output = 0
	result, err = b.settle(d)
	if err != nil || result["charged_cents"].(int64) != 0 {
		t.Fatal("small calls should share rounding", result, err)
	}
	d.ID = strings.Repeat("c", 32)
	b.authorize(d)
	d.Metered = false
	result, err = b.settle(d)
	if err != nil || result["pending_reconciliation"] != true {
		t.Fatal("unknown usage treated as free", result, err)
	}
	var held int64
	store.DB.QueryRow("SELECT reserved_cents FROM billing_calls WHERE id=?", d.ID).Scan(&held)
	if held != 2120 {
		t.Fatal(held)
	}
	other, _ := registered(t, s, "no-credit")
	store.saveTaskConfig(other.ID, "empty-job", cfg)
	d.UserID = other.ID
	d.JobID = "empty-job"
	d.ID = strings.Repeat("d", 32)
	if _, err = b.authorize(d); err == nil {
		t.Fatal("unfunded external request authorized")
	}
}
func TestOfficialRateTimeAndCache(t *testing.T) {
	b := &Billing{Prices: PriceBook{EndpointSuffix: ".example.org", Rates: []Rate{{Model: "flash", Input: 2000000, Output: 8000000, Cached: 200000, MaxInput: 1000000, Offpeak: true}}}}
	peak, _ := b.rate("flash", "https://api.example.org/v1", time.Date(2026, 10, 19, 8, 0, 0, 0, time.UTC))
	off, _ := b.rate("flash", "https://api.example.org/v1", time.Date(2026, 10, 19, 16, 0, 0, 0, time.UTC))
	if peak.Input != 2000000 || off.Input != 1000000 {
		t.Fatal(peak, off)
	}
	if _, err := b.rate("unknown", "https://api.example.org/v1", time.Now()); err == nil {
		t.Fatal("unpriced model accepted")
	}
	if _, err := b.rate("flash", "https://unverified.test/v1", time.Now()); err == nil {
		t.Fatal("unverified endpoint accepted")
	}
}

func TestImportedAPIKeyEnvironmentReferences(t *testing.T) {
	t.Setenv("C2V_IMPORT_TEST_KEY", "  private-test-value  ")
	value, err := importedAPIKey("${C2V_IMPORT_TEST_KEY}")
	if err != nil || value != "private-test-value" {
		t.Fatal("environment key was not resolved")
	}
	value, err = importedAPIKey(" literal-test-value ")
	if err != nil || value != "literal-test-value" {
		t.Fatal("literal key changed")
	}
	t.Setenv("C2V_IMPORT_TEST_KEY", "")
	for _, value := range []string{"${C2V_IMPORT_TEST_KEY}", "prefix-${C2V_IMPORT_TEST_KEY}", "${bad-name}"} {
		if _, err := importedAPIKey(value); err == nil {
			t.Fatal("unresolved placeholder accepted")
		}
	}
	c := defaultConfig()
	c.Text.APIKey = "${C2V_IMPORT_TEST_KEY}"
	if err := normalizeConfig(&c, defaultConfig()); err == nil {
		t.Fatal("personal configuration accepted environment placeholder")
	}
}
