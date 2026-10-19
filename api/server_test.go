package main

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

func fixture(t *testing.T) (*Store, *Server) {
	t.Helper()
	dir := t.TempDir()
	s, err := openStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.DB.Close() })
	if err = s.bootstrap(); err != nil {
		t.Fatal(err)
	}
	dist := filepath.Join(dir, "dist")
	os.Mkdir(dist, 0700)
	os.WriteFile(filepath.Join(dist, "index.html"), []byte("public login page"), 0600)
	server, err := newServer(s, dist, filepath.Join(dir, "worker.sock"), []string{"https://studio.test"})
	if err != nil {
		t.Fatal(err)
	}
	return s, server
}
func call(t *testing.T, s *Server, method, path string, data any, cookie *http.Cookie, bearer string) *httptest.ResponseRecorder {
	t.Helper()
	var body io.Reader
	if data != nil {
		b, _ := json.Marshal(data)
		body = bytes.NewReader(b)
	}
	r := httptest.NewRequest(method, path, body)
	r.Header.Set("Content-Type", "application/json")
	r.Header.Set("X-Frame-Request", "1")
	if cookie != nil {
		r.AddCookie(cookie)
	}
	if bearer != "" {
		r.Header.Set("Authorization", "Bearer "+bearer)
	}
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	return w
}
func registered(t *testing.T, s *Server, name string) (User, *http.Cookie) {
	t.Helper()
	w := call(t, s, "POST", "/api/auth/register", map[string]string{"username": name, "password": "a-long-password-123"}, nil, "")
	if w.Code != 201 {
		t.Fatal(w.Code, w.Body.String())
	}
	var u User
	json.Unmarshal(w.Body.Bytes(), &u)
	return u, w.Result().Cookies()[0]
}
func TestAccountsAndBoundaries(t *testing.T) {
	store, s := fixture(t)
	if w := call(t, s, "GET", "/", nil, nil, ""); w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	if w := call(t, s, "GET", "/api/jobs", nil, nil, ""); w.Code != 401 {
		t.Fatal(w.Code)
	}
	alice, a := registered(t, s, "alice")
	bob, b := registered(t, s, "bob")
	if alice.Role != "user" || bob.Balance != 0 {
		t.Fatal("registration privilege escalation")
	}
	if !a.HttpOnly || a.SameSite != http.SameSiteLaxMode {
		t.Fatal("unsafe cookie")
	}
	if w := call(t, s, "GET", "/api/admin/users", nil, a, ""); w.Code != 403 {
		t.Fatal(w.Code)
	}
	r := httptest.NewRequest("POST", "/api/auth/login", strings.NewReader(`{"username":"alice","password":"a-long-password-123"}`))
	r.Header.Set("Origin", "https://evil.test")
	r.Header.Set("X-Frame-Request", "1")
	w := httptest.NewRecorder()
	s.ServeHTTP(w, r)
	if w.Code != 403 {
		t.Fatal("foreign origin allowed")
	}
	r = httptest.NewRequest("POST", "/api/auth/logout", nil)
	r.AddCookie(a)
	w = httptest.NewRecorder()
	s.ServeHTTP(w, r)
	if w.Code != 403 {
		t.Fatal("CSRF header not required")
	}
	c := defaultConfig()
	c.Text.BaseURL = "https://example.com/v1"
	c.Text.APIKey = "secret-user-alice-key"
	c.Text.Model = "flexible-model"
	if err := store.saveConfig(alice.ID, c); err != nil {
		t.Fatal(err)
	}
	w = call(t, s, "GET", "/api/config", nil, a, "")
	if strings.Contains(w.Body.String(), c.Text.APIKey) || !strings.Contains(w.Body.String(), "flexible-model") {
		t.Fatal(w.Body.String())
	}
	w = call(t, s, "GET", "/api/config", nil, b, "")
	if strings.Contains(w.Body.String(), "flexible-model") {
		t.Fatal("config crossed owners")
	}
	raw, _ := os.ReadFile(store.DBPath())
	if bytes.Contains(raw, []byte(c.Text.APIKey)) {
		t.Fatal("plaintext secret in db")
	}
	w = call(t, s, "POST", "/api/api-keys", map[string]string{"name": "automation"}, a, "")
	if w.Code != 201 {
		t.Fatal(w.Body.String())
	}
	var token struct{ ID, Key string }
	json.Unmarshal(w.Body.Bytes(), &token)
	if w = call(t, s, "GET", "/api/config", nil, nil, token.Key); w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	if w = call(t, s, "GET", "/api/admin/users", nil, nil, token.Key); w.Code != 403 {
		t.Fatal("API key gained admin access")
	}
	call(t, s, "DELETE", "/api/api-keys/"+token.ID, nil, b, "")
	if w = call(t, s, "GET", "/api/config", nil, nil, token.Key); w.Code != 200 {
		t.Fatal("another user revoked token")
	}
	call(t, s, "DELETE", "/api/api-keys/"+token.ID, nil, a, "")
	if w = call(t, s, "GET", "/api/config", nil, nil, token.Key); w.Code != 401 {
		t.Fatal("revoked token usable")
	}
	login := call(t, s, "POST", "/api/auth/login", map[string]string{"username": "alice", "password": "a-long-password-123"}, nil, "")
	other := login.Result().Cookies()[0]
	w = call(t, s, "PUT", "/api/auth/password", map[string]string{"current_password": "a-long-password-123", "new_password": "changed-password-123"}, a, "")
	if w.Code != 200 {
		t.Fatal(w.Body.String())
	}
	if call(t, s, "GET", "/api/auth/me", nil, other, "").Code != 401 {
		t.Fatal("password change retained old session")
	}
	if call(t, s, "GET", "/api/auth/me", nil, w.Result().Cookies()[0], "").Code != 200 {
		t.Fatal("replacement session invalid")
	}
}
func (s *Store) DBPath() string { return filepath.Join(s.Dir, "users.sqlite3") }
func TestCreditsIdempotencyAndPersistence(t *testing.T) {
	store, s := fixture(t)
	u, c := registered(t, s, "customer")
	actor := store.adminID()
	const requestID = "idempotency-request-0001"
	var wg sync.WaitGroup
	errs := make(chan error, 10)
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := store.credit(actor, u.ID, 12345, "manual deposit", requestID)
			errs <- err
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		if err != nil {
			t.Fatal(err)
		}
	}
	actual, _ := store.user(u.ID)
	if actual.Balance != 12345 {
		t.Fatal("duplicate credit", actual.Balance)
	}
	entries, _ := store.ledger(u.ID)
	if len(entries) != 1 {
		t.Fatal(len(entries))
	}
	if _, err := store.credit(actor, u.ID, 99, "different", requestID); err == nil {
		t.Fatal("conflicting key accepted")
	}
	if call(t, s, "POST", "/api/admin/users/"+u.ID+"/credit", map[string]any{"amount_cents": 5, "note": "bad credit", "request_id": "bad-credit-00000000"}, c, "").Code != 403 {
		t.Fatal("user credited own account")
	}
	cfg := defaultConfig()
	cfg.Text.APIKey = "encrypted-task-key"
	cfg.Text.Model = "original"
	store.saveTaskConfig(u.ID, "job0001", cfg)
	cfg.Text.Model = "changed"
	store.saveConfig(u.ID, cfg)
	frozen, err := store.taskConfig(u.ID, "job0001")
	if err != nil || frozen.Text.Model != "original" {
		t.Fatal("task config not frozen")
	}
	if _, err = store.taskConfig("another-user", "job0001"); err == nil {
		t.Fatal("task config leaked")
	}
	reopened, err := openStore(store.Dir)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.DB.Close()
	again, _ := reopened.user(u.ID)
	if again.Balance != 12345 {
		t.Fatal("balance lost across restart")
	}
	saved, err := reopened.config(u.ID)
	if err != nil || saved.Text.APIKey != "encrypted-task-key" {
		t.Fatal("encrypted config lost")
	}
}
func TestEndpointAndAccountStatus(t *testing.T) {
	for _, endpoint := range []string{"http://example.com/v1", "https://127.0.0.1/v1", "https://[::1]/v1", "https://169.254.169.254/v1", "https://100.64.0.1/v1", "https://example.com:8080/v1", "https://user:password@example.com/v1"} {
		if err := validateEndpoint(endpoint); err == nil {
			t.Fatal("unsafe endpoint", endpoint)
		}
	}
	store, s := fixture(t)
	u, c := registered(t, s, "disabled")
	raw := "frame_" + randomID(32)
	store.DB.Exec("INSERT INTO api_tokens(id,user_id,name,token_hash,prefix,created_at) VALUES(?,?,?,?,?,?)", randomID(16), u.ID, "test", hashToken(raw), raw[:14], 1)
	store.DB.Exec("UPDATE users SET active=0 WHERE id=?", u.ID)
	if call(t, s, "GET", "/api/auth/me", nil, c, "").Code != 401 || call(t, s, "GET", "/api/jobs", nil, nil, raw).Code != 401 {
		t.Fatal("disabled account authenticated")
	}
}

func TestSessionRevocationAndLogout(t *testing.T) {
	_, s := fixture(t)
	_, alice := registered(t, s, "session-alice")
	_, bob := registered(t, s, "session-bob")
	login := call(t, s, "POST", "/api/auth/login", map[string]string{"username": "session-alice", "password": "a-long-password-123"}, nil, "")
	if login.Code != 200 {
		t.Fatal(login.Code)
	}
	other := login.Result().Cookies()[0]
	var sessions []struct {
		ID      string
		Current bool
	}
	response := call(t, s, "GET", "/api/auth/sessions", nil, alice, "")
	if err := json.Unmarshal(response.Body.Bytes(), &sessions); err != nil || len(sessions) != 2 {
		t.Fatal(response.Body.String(), err)
	}
	var target string
	for _, session := range sessions {
		if !session.Current {
			target = session.ID
		}
	}
	if target == "" {
		t.Fatal("second session missing")
	}
	call(t, s, "DELETE", "/api/auth/sessions/"+target, nil, bob, "")
	if call(t, s, "GET", "/api/auth/me", nil, other, "").Code != 200 {
		t.Fatal("another user revoked session")
	}
	if call(t, s, "DELETE", "/api/auth/sessions/"+target, nil, alice, "").Code != 200 {
		t.Fatal("session revocation failed")
	}
	if call(t, s, "GET", "/api/auth/me", nil, other, "").Code != 401 {
		t.Fatal("revoked session remains usable")
	}
	if call(t, s, "GET", "/api/auth/me", nil, alice, "").Code != 200 {
		t.Fatal("revoking second session logged out current session")
	}
	logout := call(t, s, "POST", "/api/auth/logout", nil, alice, "")
	if logout.Code != 200 || len(logout.Result().Cookies()) != 1 || logout.Result().Cookies()[0].MaxAge != -1 {
		t.Fatal("logout failed to clear browser cookie")
	}
	if call(t, s, "GET", "/api/auth/me", nil, alice, "").Code != 401 {
		t.Fatal("logout left server session usable")
	}
	if call(t, s, "GET", "/api/auth/me", nil, bob, "").Code != 200 {
		t.Fatal("logout affected another user")
	}
}

func TestStartupRejectsBillingInitializationFailure(t *testing.T) {
	store, _ := fixture(t)
	t.Setenv("C2V_BILLING_ENABLED", "true")
	server, err := newServer(store, t.TempDir(), "unused.sock", nil)
	if err == nil || server != nil {
		t.Fatal("missing price book must fail startup when billing is enabled")
	}
	t.Setenv("C2V_BILLING_ENABLED", "false")
	if err = store.DB.Close(); err != nil {
		t.Fatal(err)
	}
	server, err = newServer(store, t.TempDir(), "unused.sock", nil)
	if err == nil || server != nil {
		t.Fatal("unavailable billing ledger must fail startup")
	}
}

func TestPreviewSessionIsolation(t *testing.T) {
	_, production := fixture(t)
	_, preview := fixture(t)
	preview.CookieName = "frame_preview_session"
	_, liveCookie := registered(t, production, "live-user")
	_, previewCookie := registered(t, preview, "preview-user")
	if liveCookie.Name == previewCookie.Name {
		t.Fatal("preview overwrites production browser session")
	}
	if call(t, preview, "GET", "/api/auth/me", nil, liveCookie, "").Code != 401 {
		t.Fatal("preview accepted production cookie")
	}
	if call(t, production, "GET", "/api/auth/me", nil, previewCookie, "").Code != 401 {
		t.Fatal("production accepted preview cookie")
	}
	if call(t, preview, "GET", "/api/auth/me", nil, previewCookie, "").Code != 200 {
		t.Fatal("preview login failed")
	}
	logout := call(t, preview, "POST", "/api/auth/logout", nil, previewCookie, "")
	if logout.Code != 200 || logout.Result().Cookies()[0].Name != previewCookie.Name {
		t.Fatal("preview logout cleared wrong cookie")
	}
	if call(t, production, "GET", "/api/auth/me", nil, liveCookie, "").Code != 200 {
		t.Fatal("preview logout affected production")
	}
}
