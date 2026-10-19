package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
)

func TestModelDiscoveryCredentialBoundaries(t *testing.T) {
	store, s := fixture(t)
	user, alice := registered(t, s, "models-alice")
	_, bob := registered(t, s, "models-bob")
	c := defaultConfig()
	c.Text.BaseURL = "https://1.1.1.1/v1"
	c.Text.APIKey = "saved-generation-secret"
	c.Vision.BaseURL = c.Text.BaseURL
	c.Vision.APIKey = "saved-vision-secret"
	if err := store.saveConfig(user.ID, c); err != nil {
		t.Fatal(err)
	}
	calls := 0
	wantKey := c.Text.APIKey
	s.ModelsClient = &http.Client{Transport: transportFunc(func(r *http.Request) (*http.Response, error) {
		calls++
		if r.Method != "GET" || r.URL.Path != "/v1/models" || r.Header.Get("Authorization") != "Bearer "+wantKey {
			t.Fatal("wrong upstream request")
		}
		if r.Header.Get("Cookie") != "" {
			t.Fatal("browser credentials forwarded")
		}
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"data":[{"id":"z-model"},{"id":"a-model"},{"id":"z-model"}]}`)), Header: http.Header{}}, nil
	})}
	input := map[string]any{"role": "text", "base_url": c.Text.BaseURL}
	result := call(t, s, "POST", "/api/config/models", input, alice, "")
	if result.Code != 200 || result.Body.String() != "{\"models\":[\"a-model\",\"z-model\"]}\n" {
		t.Fatal(result.Code, result.Body.String())
	}
	if call(t, s, "POST", "/api/config/models", input, bob, "").Code != 422 || calls != 1 {
		t.Fatal("another user's saved key was reused")
	}
	input["base_url"] = "https://8.8.8.8/v1"
	if call(t, s, "POST", "/api/config/models", input, alice, "").Code != 422 || calls != 1 {
		t.Fatal("saved key sent to changed endpoint")
	}
	input["base_url"] = c.Text.BaseURL
	input["clear_key"] = true
	if call(t, s, "POST", "/api/config/models", input, alice, "").Code != 422 || calls != 1 {
		t.Fatal("removed key was reused")
	}
	delete(input, "clear_key")
	input["role"] = "vision"
	wantKey = c.Vision.APIKey
	if call(t, s, "POST", "/api/config/models", input, alice, "").Code != 200 {
		t.Fatal("independent vision key not used")
	}
	input["api_key"] = "draft-secret"
	wantKey = "draft-secret"
	if call(t, s, "POST", "/api/config/models", input, alice, "").Code != 200 {
		t.Fatal("draft key not usable")
	}
	saved, err := store.config(user.ID)
	if err != nil || saved.Vision.APIKey != c.Vision.APIKey {
		t.Fatal("fetch persisted draft key")
	}
	input["base_url"] = "https://127.0.0.1/v1"
	before := calls
	if call(t, s, "POST", "/api/config/models", input, alice, "").Code != 422 || calls != before {
		t.Fatal("private upstream allowed")
	}
	if call(t, s, "POST", "/api/config/models", input, nil, "").Code != 401 {
		t.Fatal("discovery allows anonymous callers")
	}
}

func TestModelDiscoveryFailureAndCatalogFormats(t *testing.T) {
	_, s := fixture(t)
	_, cookie := registered(t, s, "models-errors")
	input := map[string]any{"role": "text", "base_url": "https://1.1.1.1/v1", "api_key": "test-secret"}
	for _, tc := range []struct {
		upstream, want int
		body           string
	}{
		{401, 422, "test-secret"}, {404, 422, "test-secret"}, {429, 429, "test-secret"},
		{302, 502, "test-secret"}, {200, 422, "invalid"}, {200, 502, strings.Repeat("x", 2*1024*1024+1)},
	} {
		s.ModelsClient = &http.Client{Transport: transportFunc(func(*http.Request) (*http.Response, error) {
			return &http.Response{StatusCode: tc.upstream, Body: io.NopCloser(strings.NewReader(tc.body)), Header: http.Header{}}, nil
		})}
		result := call(t, s, "POST", "/api/config/models", input, cookie, "")
		if result.Code != tc.want || strings.Contains(result.Body.String(), "test-secret") {
			t.Fatal(result.Code, result.Body.String())
		}
	}
	for _, body := range []string{`{"data":[{"id":"a"}]}`, `{"models":[{"name":"a"}]}`, `["a"]`} {
		models, err := parseModels([]byte(body))
		if err != nil || len(models) != 1 || models[0] != "a" {
			t.Fatal(body, models, err)
		}
	}
	for _, body := range []string{`{}`, `null`, `{"error":"denied"}`} {
		if _, err := parseModels([]byte(body)); err == nil {
			t.Fatal("invalid catalog accepted", body)
		}
	}
	models, err := parseModels([]byte(`{"data":[]}`))
	if err != nil || len(models) != 0 {
		t.Fatal("empty catalog failed")
	}
	// The production transport must refuse internal destinations even at dial time.
	client := publicModelClient()
	if client.CheckRedirect(nil, nil) != http.ErrUseLastResponse {
		t.Fatal("redirects enabled")
	}
	transport := client.Transport.(*http.Transport)
	if transport.Proxy != nil {
		t.Fatal("environment proxy enabled")
	}
	if conn, err := transport.DialContext(context.Background(), "tcp", "127.0.0.1:443"); err == nil {
		conn.Close()
		t.Fatal("private address dialed")
	}
	// A clear Chinese failure is returned, never a raw upstream body.
	var body map[string]any
	json.Unmarshal(call(t, s, "POST", "/api/config/models", map[string]any{"role": "unknown"}, cookie, "").Body.Bytes(), &body)
	if body["detail"] == nil {
		t.Fatal("missing validation detail")
	}
}
