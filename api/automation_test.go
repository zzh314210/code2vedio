package main

import (
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strings"
	"testing"
)

type transportFunc func(*http.Request) (*http.Response, error)

func (f transportFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }
func TestAutomationJSONAndFrozenConfig(t *testing.T) {
	store, s := fixture(t)
	u, cookie := registered(t, s, "api-creator")
	config := defaultConfig()
	config.VisionInherit = true // This fixture deliberately uses one model for both roles.
	config.Text.BaseURL = "https://example.com/v1"
	config.Text.Model = "custom-model"
	config.Text.APIKey = "test-caller-secret"
	store.saveConfig(u.ID, config)
	keyResponse := call(t, s, "POST", "/api/api-keys", map[string]string{"name": "integration"}, cookie, "")
	var key struct{ Key string }
	json.Unmarshal(keyResponse.Body.Bytes(), &key)
	var identity string
	s.Proxy.Transport = transportFunc(func(r *http.Request) (*http.Response, error) {
		if r.Header.Get("Cookie") != "" || r.Header.Get("Authorization") != "" {
			t.Fatal("public credentials forwarded to worker")
		}
		raw, err := base64.RawURLEncoding.DecodeString(r.Header.Get("X-Frame-Context"))
		if err != nil {
			t.Fatal(err)
		}
		var context struct {
			User   struct{ ID string }
			JobID  string `json:"job_id"`
			Config PersonalConfig
		}
		if err = json.Unmarshal(raw, &context); err != nil {
			t.Fatal(err)
		}
		if context.User.ID != u.ID || context.Config.Text.APIKey != "test-caller-secret" {
			t.Fatal("wrong worker context")
		}
		identity = context.JobID
		body, _ := io.ReadAll(r.Body)
		form, err := url.ParseQuery(string(body))
		if err != nil {
			t.Fatal(err)
		}
		if form.Get("prompt") != "制作手绘行测视频" || form.Get("style") != "studio_sketch" || form.Get("auto_approve") != "true" || form.Get("source_ids") != "[]" {
			t.Fatal(form)
		}
		return &http.Response{StatusCode: 202, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(strings.NewReader(`{"id":"` + identity + `"}`))}, nil
	})
	response := call(t, s, "POST", "/api/jobs", map[string]any{"prompt": "制作手绘行测视频", "style": "studio_sketch", "duration": 60, "auto_approve": true}, nil, key.Key)
	if response.Code != 202 || identity == "" {
		t.Fatal(response.Code, response.Body.String())
	}
	frozen, err := store.taskConfig(u.ID, identity)
	if err != nil || frozen.Text.Model != "custom-model" {
		t.Fatal("task config not archived")
	}
	config.Text.Model = "later-model"
	store.saveConfig(u.ID, config)
	frozen, _ = store.taskConfig(u.ID, identity)
	if frozen.Text.Model != "custom-model" {
		t.Fatal("configuration drift")
	}
}
