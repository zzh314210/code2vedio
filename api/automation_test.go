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

func TestQueueAdministrationRequiresAdminSession(t *testing.T) {
	store, s := fixture(t)
	u, cookie := registered(t, s, "queue-admin")
	forwarded := 0
	s.Proxy.Transport = transportFunc(func(r *http.Request) (*http.Response, error) {
		forwarded++
		raw, err := base64.RawURLEncoding.DecodeString(r.Header.Get("X-Frame-Context"))
		if err != nil {
			t.Fatal(err)
		}
		var context struct{ User struct{ ID, Role string } }
		if err := json.Unmarshal(raw, &context); err != nil {
			t.Fatal(err)
		}
		if context.User.ID != u.ID || context.User.Role != "admin" {
			t.Fatal("admin identity was not signed for worker")
		}
		return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(strings.NewReader(`{"ok":true}`))}, nil
	})
	for _, path := range []string{"/api/admin/queue", "/api/admin/queue/order", "/api/admin/queue/1"} {
		if response := call(t, s, "GET", path, nil, nil, ""); response.Code != 401 {
			t.Fatal("anonymous queue access", response.Code)
		}
		if response := call(t, s, "GET", path, nil, cookie, ""); response.Code != 403 {
			t.Fatal("user queue administration", response.Code)
		}
	}
	if forwarded != 0 {
		t.Fatal("unauthorized queue request reached worker")
	}
	if _, err := store.DB.Exec("UPDATE users SET role='admin' WHERE id=?", u.ID); err != nil {
		t.Fatal(err)
	}
	if response := call(t, s, "GET", "/api/admin/queue", nil, cookie, ""); response.Code != 200 {
		t.Fatal(response.Code)
	}
	keyResponse := call(t, s, "POST", "/api/api-keys", map[string]string{"name": "queue-test"}, cookie, "")
	var key struct{ Key string }
	json.Unmarshal(keyResponse.Body.Bytes(), &key)
	if key.Key == "" {
		t.Fatal("test API key not created")
	}
	if response := call(t, s, "GET", "/api/admin/queue", nil, nil, key.Key); response.Code != 403 {
		t.Fatal("API token may not administer queue", response.Code)
	}
	if forwarded != 1 {
		t.Fatal("unexpected queue forwarding", forwarded)
	}
}

func TestFilmRevisionFreezesParentConfiguration(t *testing.T) {
	store, s := fixture(t)
	u, cookie := registered(t, s, "film-reviser")
	parent := defaultConfig()
	parent.VisionInherit = true
	parent.Text.BaseURL = "https://example.com/v1"
	parent.Text.Model = "original-film-model"
	parent.Text.APIKey = "original-film-test-key"
	if err := store.saveTaskConfig(u.ID, "parent-film", parent); err != nil {
		t.Fatal(err)
	}
	current := parent
	current.Text.Model = "later-account-model"
	store.saveConfig(u.ID, current)
	var child string
	s.Proxy.Transport = transportFunc(func(r *http.Request) (*http.Response, error) {
		raw, err := base64.RawURLEncoding.DecodeString(r.Header.Get("X-Frame-Context"))
		if err != nil {
			t.Fatal(err)
		}
		var context struct {
			JobID  string `json:"job_id"`
			Config PersonalConfig
		}
		if err := json.Unmarshal(raw, &context); err != nil {
			t.Fatal(err)
		}
		if context.Config.Text.Model != "original-film-model" {
			t.Fatal("revision drifted to account configuration")
		}
		if r.Method == "POST" && strings.HasSuffix(r.URL.Path, "/revisions") {
			child = context.JobID
			if child == "" || child == "parent-film" {
				t.Fatal("revision requires a separate task identity")
			}
			var body map[string]any
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				t.Fatal(err)
			}
			if body["feedback"] != "缩短开头，保留推理过程" {
				t.Fatal("revision JSON was rewritten")
			}
		} else if context.JobID != "" {
			t.Fatal("read-only advice polling created a task")
		}
		return &http.Response{StatusCode: 202, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(strings.NewReader(`{"id":"` + child + `"}`))}, nil
	})
	response := call(t, s, "POST", "/api/jobs/parent-film/revisions", map[string]any{"feedback": "缩短开头，保留推理过程", "auto_approve": false}, cookie, "")
	if response.Code != 202 {
		t.Fatal(response.Code, response.Body.String())
	}
	frozen, err := store.taskConfig(u.ID, child)
	if err != nil || frozen.Text.Model != "original-film-model" {
		t.Fatal("child configuration not frozen independently")
	}
	response = call(t, s, "GET", "/api/jobs/parent-film/revision-advice", nil, cookie, "")
	if response.Code != 202 {
		t.Fatal(response.Code)
	}
}
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
		if form.Get("prompt") != "制作手绘行测视频" || form.Get("style") != "studio_sketch" || form.Get("auto_approve") != "true" || form.Get("source_ids") != "[]" || form.Get("template_id") != "explainer" || form.Get("bgm_enabled") != "true" || form.Get("bgm_track_id") != "easy-lemon" || form.Get("bgm_volume") != "0" {
			t.Fatal(form)
		}
		return &http.Response{StatusCode: 202, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(strings.NewReader(`{"id":"` + identity + `"}`))}, nil
	})
	response := call(t, s, "POST", "/api/jobs", map[string]any{"prompt": "制作手绘行测视频", "style": "studio_sketch", "duration": 60, "auto_approve": true, "template_id": "explainer", "bgm_enabled": true, "bgm_track_id": "easy-lemon", "bgm_volume": 0}, nil, key.Key)
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

// Editing uploads must freeze the same private model configuration as creation;
// later export/retry must not silently use newly edited account credentials.
func TestEditingBearerFrozenConfiguration(t *testing.T) {
	store, s := fixture(t)
	u, cookie := registered(t, s, "edit-creator")
	cfg := defaultConfig()
	cfg.VisionInherit = true
	cfg.Text.BaseURL = "https://example.com/v1"
	cfg.Text.Model = "edit-original"
	cfg.Text.APIKey = "editing-test-secret"
	if err := store.saveConfig(u.ID, cfg); err != nil {
		t.Fatal(err)
	}
	response := call(t, s, "POST", "/api/api-keys", map[string]string{"name": "editing"}, cookie, "")
	var key struct{ Key string }
	json.Unmarshal(response.Body.Bytes(), &key)
	var identity string
	s.Proxy.Transport = transportFunc(func(r *http.Request) (*http.Response, error) {
		raw, err := base64.RawURLEncoding.DecodeString(r.Header.Get("X-Frame-Context"))
		if err != nil {
			t.Fatal(err)
		}
		var c struct {
			JobID  string `json:"job_id"`
			Config PersonalConfig
		}
		if err = json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		if c.Config.Text.Model != "edit-original" || c.Config.Text.APIKey != "editing-test-secret" {
			t.Fatal("editing config drift")
		}
		if r.Header.Get("Authorization") != "" || r.Header.Get("Cookie") != "" {
			t.Fatal("public credentials forwarded")
		}
		if r.URL.Path == "/api/edits" {
			identity = c.JobID
		}
		return &http.Response{StatusCode: 202, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(strings.NewReader(`{"id":"` + identity + `"}`))}, nil
	})
	// Transport fixture only: the worker's real multipart/media validation is tested
	// by editing_api_smoke.py. Here verify the public API route and signed context.
	response = call(t, s, "POST", "/api/edits", nil, nil, key.Key)
	if response.Code != 202 || identity == "" {
		t.Fatal(response.Code, response.Body.String())
	}
	frozen, err := store.taskConfig(u.ID, identity)
	if err != nil || frozen.Text.Model != "edit-original" {
		t.Fatal("editing config not archived")
	}
	cfg.Text.Model = "new-account-model"
	cfg.Text.APIKey = "different-test-secret"
	store.saveConfig(u.ID, cfg)
	for _, action := range []string{"render", "retry"} {
		response = call(t, s, "POST", "/api/edits/"+identity+"/"+action, nil, nil, key.Key)
		if response.Code != 202 {
			t.Fatal(action, response.Code, response.Body.String())
		}
	}
}

func TestMusicUploadsAllowBearerWithoutModelCharge(t *testing.T) {
	store, s := fixture(t)
	u, cookie := registered(t, s, "music-uploader")
	response := call(t, s, "POST", "/api/api-keys", map[string]string{"name": "music"}, cookie, "")
	var key struct{ Key string }
	json.Unmarshal(response.Body.Bytes(), &key)
	s.Proxy.Transport = transportFunc(func(r *http.Request) (*http.Response, error) {
		raw, err := base64.RawURLEncoding.DecodeString(r.Header.Get("X-Frame-Context"))
		if err != nil {
			t.Fatal(err)
		}
		var context struct {
			JobID string `json:"job_id"`
			User  struct{ ID string }
		}
		if err = json.Unmarshal(raw, &context); err != nil {
			t.Fatal(err)
		}
		if context.JobID != "" || context.User.ID != u.ID {
			t.Fatal("Music operation admitted a model task or wrong owner")
		}
		return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(strings.NewReader(`[]`))}, nil
	})
	for _, method := range []string{"GET", "POST"} {
		response = call(t, s, method, "/api/music/uploads", nil, nil, key.Key)
		if response.Code != 200 {
			t.Fatal(method, response.Code, response.Body.String())
		}
	}
	var count int
	if err := store.DB.QueryRow("SELECT count(*) FROM task_configs WHERE user_id=?", u.ID).Scan(&count); err != nil || count != 0 {
		t.Fatal("Music created a model configuration", err, count)
	}
}
