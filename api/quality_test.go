package main

import (
	"encoding/json"
	"sync"
	"testing"
)

func TestQualityAtomicSpendingCapAndAcceptanceRole(t *testing.T) {
	store, s := fixture(t)
	s.Billing.Enabled = true
	catalog := testCatalog()
	extra := catalog.Models[0]
	extra.ID = "criteria-model"
	extra.Channel.Model = "criteria-generator"
	extra.Price.Model = "criteria-generator"
	extra.Price.Output = 4000000
	catalog.Models = append(catalog.Models, extra)
	store.saveCatalog(catalog, store.adminID())
	u, _ := registered(t, s, "quality-paid")
	store.credit(store.adminID(), u.ID, 10000, "test deposit", "quality-deposit-01")
	cfg := defaultConfig()
	cfg.UsePlatform = true
	cfg.PlatformAcceptance = extra.ID
	cfg, _ = s.effective(cfg)
	cfg.Quality.MaxCostCents = 22
	if cfg.Acceptance.Model != "criteria-generator" || cfg.PlatformPrices[2].Model != "criteria-generator" {
		t.Fatal("acceptance not independently selected")
	}
	public, _ := json.Marshal(cfg.public())
	if string(public) == "" {
		t.Fatal("missing public config")
	}
	store.saveTaskConfig(u.ID, "quality-capped", cfg)
	var wg sync.WaitGroup
	var mu sync.Mutex
	accepted := []meterRequest{}
	for i := 0; i < 12; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			d := meterRequest{ID: randomID(16), UserID: u.ID, JobID: "quality-capped", Role: "text", Model: "generation", MaxOutput: 24000, InputBound: 10000}
			if _, e := s.Billing.authorize(d); e == nil {
				mu.Lock()
				accepted = append(accepted, d)
				mu.Unlock()
			}
		}()
	}
	wg.Wait()
	if len(accepted) != 1 {
		t.Fatal("concurrent cap exceeded", len(accepted))
	}
	first := accepted[0]
	if _, e := s.Billing.authorize(first); e != nil {
		t.Fatal("idempotent authorization blocked", e)
	}
	first.Metered = true
	first.Input = 1000
	first.Output = 100
	s.Billing.settle(first)
	first.ID = randomID(16)
	if _, e := s.Billing.authorize(first); e == nil {
		t.Fatal("settled spend excluded from cap")
	}
	first.MaxOutput = 10000
	first.Role = "acceptance"
	first.Model = "criteria-generator"
	if _, e := s.Billing.authorize(first); e != nil {
		t.Fatal("independent acceptance call rejected", e)
	}
	// BYOK must not use our money ledger or require a deposit.
	personal := defaultConfig()
	personal.Quality.MaxCostCents = 1
	store.saveTaskConfig(u.ID, "quality-byok", personal)
	first.ID = randomID(16)
	first.JobID = "quality-byok"
	result, e := s.Billing.authorize(first)
	if e != nil || result["billing"] != false {
		t.Fatal("BYOK entered local billing", result, e)
	}
	var count int
	store.DB.QueryRow("SELECT count(*) FROM billing_calls WHERE job_id='quality-byok'").Scan(&count)
	if count != 0 {
		t.Fatal("BYOK usage recorded")
	}
}

func TestQualityEstimateSettingsAndValidation(t *testing.T) {
	c := defaultConfig()
	c.PlatformPrices = []Rate{{Role: "text", Input: 2000000, Output: 8000000, MaxInput: 1000000}, {Role: "vision", Input: 800000, Output: 2700000, MaxInput: 1000000}, {Role: "acceptance", Input: 2000000, Output: 8000000, MaxInput: 1000000}}
	c.Quality = &QualityPolicy{MaxCalls: 120, SampleSeconds: 3}
	low, high, calls := qualityEstimate(c, 120)
	c.Quality.Visual = 2
	c.Quality.Final = 2
	c.Quality.Code = 2
	low2, high2, _ := qualityEstimate(c, 120)
	if low2 != low || high2 <= high {
		t.Fatal("revisions not reflected", low, high, low2, high2)
	}
	c.Quality.SampleSeconds = .5
	denseLow, denseHigh, denseCalls := qualityEstimate(c, 120)
	if denseLow <= low || denseHigh < high2 || denseCalls <= calls {
		t.Fatal("density not reflected")
	}
	c.Quality.MaxCalls = 1
	_, cappedHigh, required := qualityEstimate(c, 120)
	if cappedHigh > denseHigh || required <= 1 {
		t.Fatal("cap or insufficient-call warning hidden")
	}
	c.Quality.MaxCalls = 0
	if validateQuality(c.Quality) == nil {
		t.Fatal("zero model-call cap accepted")
	}
	c.Quality = defaultQuality()
	c.Quality.Final = 6
	if validateQuality(c.Quality) == nil {
		t.Fatal("unbounded corrections accepted")
	}
}

func TestQualitySwitchesIndependentOnDecode(t *testing.T) {
	c := defaultConfig()
	raw := []byte(`{"subtitles_enabled":false,"acceptance_inherit":true,"text":{"thinking_enabled":true},"vision":{"thinking_enabled":false},"acceptance":{"thinking_enabled":true}}`)
	if e := json.Unmarshal(raw, &c); e != nil {
		t.Fatal(e)
	}
	if *c.Subtitles || !*c.AcceptanceInherit || !*c.Text.Thinking || *c.Vision.Thinking || !*c.Acceptance.Thinking {
		t.Fatal("switch pointers alias across unrelated settings")
	}
	raw, _ = json.Marshal(c)
	saved := defaultConfig()
	json.Unmarshal(raw, &saved)
	if *saved.Subtitles || !*saved.AcceptanceInherit || !*saved.Text.Thinking || *saved.Vision.Thinking {
		t.Fatal("switches changed on persistence round trip")
	}
}
