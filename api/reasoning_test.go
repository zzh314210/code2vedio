package main

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
)

func TestReasoningConfigurationSurvivesEncryptedStorage(t *testing.T) {
	store, s := fixture(t)
	user, cookie := registered(t, s, "reasoning-user")
	c := defaultConfig()
	c.Text.Provider = "deepseek"
	c.Text.ExtraBody = map[string]any{"thinking": map[string]any{"type": "enabled"}, "reasoning_effort": "max"}
	if err := normalizeConfig(&c, defaultConfig()); err != nil {
		t.Fatal(err)
	}
	if c.Text.Thinking == nil || !*c.Text.Thinking || c.Text.ReasoningEffort != "max" {
		t.Fatal("reasoning defaults missing")
	}
	if err := store.saveConfig(user.ID, c); err != nil {
		t.Fatal(err)
	}
	saved, err := store.config(user.ID)
	if err != nil {
		t.Fatal(err)
	}
	if saved.Text.Provider != "deepseek" || saved.Text.ExtraBody["reasoning_effort"] != "max" {
		t.Fatal("reasoning discarded")
	}
	r := call(t, s, "GET", "/api/config", nil, cookie, "")
	var public PersonalConfig
	if r.Code != 200 || json.Unmarshal(r.Body.Bytes(), &public) != nil || public.Text.ReasoningEffort != "max" {
		t.Fatal("public configuration lost reasoning", r.Body.String())
	}
	bad := c
	bad.Text.ReasoningEffort = "infinite"
	if normalizeConfig(&bad, c) == nil {
		t.Fatal("invalid effort accepted")
	}
	bad = c
	bad.Text.ExtraBody = map[string]any{"messages": []string{"overwrite"}}
	if normalizeConfig(&bad, c) == nil {
		t.Fatal("request body override accepted")
	}
}

func TestClaudeModelListUsesNativeAuthentication(t *testing.T) {
	_, s := fixture(t)
	_, cookie := registered(t, s, "claude-list")
	s.ModelsClient = &http.Client{Transport: transportFunc(func(r *http.Request) (*http.Response, error) {
		if r.Header.Get("x-api-key") != "native-key" || r.Header.Get("anthropic-version") != "2023-06-01" || r.Header.Get("Authorization") != "" {
			t.Fatal("incorrect Claude authentication")
		}
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"data":[{"id":"claude-model"}]}`)), Header: http.Header{}}, nil
	})}
	r := call(t, s, "POST", "/api/config/models", map[string]any{"role": "text", "provider": "anthropic", "api_key": "native-key", "base_url": "https://1.1.1.1/v1"}, cookie, "")
	if r.Code != 200 || !strings.Contains(r.Body.String(), "claude-model") {
		t.Fatal(r.Code, r.Body.String())
	}
}

func TestLegacyCatalogReasoningUpgradePreservesCredentialsAndPrice(t *testing.T) {
	store, _ := fixture(t)
	c := PlatformCatalog{Models: []PlatformModel{{ID: "model-old", Role: "text", Label: "Legacy", Channel: Channel{Model: "deepseek", BaseURL: "https://api.aliyuncs.com/v1", APIKey: "keep-secret", MaxTokens: 6000}, Price: Rate{Model: "deepseek", Input: 100, Output: 200}}}}
	if err := store.saveCatalog(c, store.adminID()); err != nil {
		t.Fatal(err)
	}
	n, err := store.upgradeReasoningDefaults()
	if err != nil || n != 1 {
		t.Fatal(n, err)
	}
	saved, _ := store.catalog()
	ch := saved.Models[0].Channel
	if ch.APIKey != "keep-secret" || ch.Provider != "dashscope" || ch.MaxTokens != 24000 || ch.Thinking == nil || !*ch.Thinking || ch.ReasoningEffort != "max" || saved.Models[0].Price.Input != 100 {
		t.Fatal("migration changed credentials/prices or missed reasoning defaults")
	}
	n, err = store.upgradeReasoningDefaults()
	if err != nil || n != 0 {
		t.Fatal("migration was not idempotent", n, err)
	}
}

func TestExplicitNonStreamingSettingSurvivesStorage(t *testing.T) {
	store, s := fixture(t)
	u, _ := registered(t, s, "nonstream-user")
	c := defaultConfig()
	if !c.Text.Stream || !c.Vision.Stream {
		t.Fatal("reasoning defaults must stream")
	}
	c.Text.Stream = false
	if err := store.saveConfig(u.ID, c); err != nil {
		t.Fatal(err)
	}
	saved, err := store.config(u.ID)
	if err != nil || saved.Text.Stream {
		t.Fatal("explicit nonstreaming setting discarded", err)
	}
}
