package main

import (
	"crypto/rand"
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

func (s *Store) initAutomation() error {
	_, err := s.DB.Exec(`CREATE TABLE IF NOT EXISTS api_tokens(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),name TEXT NOT NULL,token_hash TEXT UNIQUE NOT NULL,prefix TEXT NOT NULL,created_at INTEGER NOT NULL,last_used_at INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS task_configs(job_id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),ciphertext BLOB NOT NULL);`)
	return err
}
func (s *Store) tokenUser(token string) (User, error) {
	if !strings.HasPrefix(token, "frame_") || len(token) > 100 {
		return User{}, sql.ErrNoRows
	}
	var uid, id string
	var last int64
	if err := s.DB.QueryRow("SELECT user_id,id,last_used_at FROM api_tokens WHERE token_hash=?", hashToken(token)).Scan(&uid, &id, &last); err != nil {
		return User{}, err
	}
	u, err := s.user(uid)
	if err != nil || !u.Active {
		return User{}, sql.ErrNoRows
	}
	if time.Now().Unix()-last > 60 {
		s.DB.Exec("UPDATE api_tokens SET last_used_at=? WHERE id=?", time.Now().Unix(), id)
	}
	return u, nil
}
func (s *Server) apiKeys(w http.ResponseWriter, r *http.Request) {
	u := current(r)
	if r.Method == "POST" {
		var d struct {
			Name string `json:"name"`
		}
		if !decode(w, r, &d) {
			return
		}
		d.Name = strings.TrimSpace(d.Name)
		if len(d.Name) < 1 || len(d.Name) > 80 {
			fail(w, 422, "请输入1至80字节的密钥名称。")
			return
		}
		var n int
		if err := s.Store.DB.QueryRow("SELECT count(*) FROM api_tokens WHERE user_id=?", u.ID).Scan(&n); err != nil {
			s.internal(w, err)
			return
		}
		if n >= 20 {
			fail(w, 400, "最多创建20个调用密钥，请先移除不用的密钥。")
			return
		}
		raw := "frame_" + randomID(32)
		id := randomID(16)
		now := time.Now().Unix()
		prefix := raw[:14]
		if _, err := s.Store.DB.Exec("INSERT INTO api_tokens(id,user_id,name,token_hash,prefix,created_at) VALUES(?,?,?,?,?,?)", id, u.ID, d.Name, hashToken(raw), prefix, now); err != nil {
			s.internal(w, err)
			return
		}
		reply(w, 201, map[string]any{"id": id, "name": d.Name, "key": raw, "prefix": prefix, "created_at": now})
		return
	}
	rows, err := s.Store.DB.Query("SELECT id,name,prefix,created_at,last_used_at FROM api_tokens WHERE user_id=? ORDER BY created_at DESC", u.ID)
	if err != nil {
		s.internal(w, err)
		return
	}
	defer rows.Close()
	items := []map[string]any{}
	for rows.Next() {
		var id, name, prefix string
		var created, last int64
		if err = rows.Scan(&id, &name, &prefix, &created, &last); err != nil {
			s.internal(w, err)
			return
		}
		items = append(items, map[string]any{"id": id, "name": name, "prefix": prefix, "created_at": created, "last_used_at": last})
	}
	reply(w, 200, items)
}
func (s *Server) revokeAPIKey(w http.ResponseWriter, r *http.Request) {
	if _, err := s.Store.DB.Exec("DELETE FROM api_tokens WHERE id=? AND user_id=?", r.PathValue("id"), current(r).ID); err != nil {
		s.internal(w, err)
		return
	}
	reply(w, 200, map[string]bool{"ok": true})
}
func (s *Store) taskConfig(uid, job string) (PersonalConfig, error) {
	var b []byte
	c := defaultConfig()
	err := s.DB.QueryRow("SELECT ciphertext FROM task_configs WHERE job_id=? AND user_id=?", job, uid).Scan(&b)
	if err != nil {
		return c, err
	}
	n := s.Cipher.NonceSize()
	if len(b) < n {
		return c, errors.New("invalid task config")
	}
	raw, err := s.Cipher.Open(nil, b[:n], b[n:], []byte(uid+":"+job))
	if err != nil {
		return c, err
	}
	err = json.Unmarshal(raw, &c)
	return c, err
}
func (s *Store) saveTaskConfig(uid, job string, c PersonalConfig) error {
	raw, err := json.Marshal(c)
	if err != nil {
		return err
	}
	nonce := make([]byte, s.Cipher.NonceSize())
	if _, err = rand.Read(nonce); err != nil {
		return err
	}
	encrypted := s.Cipher.Seal(nonce, nonce, raw, []byte(uid+":"+job))
	_, err = s.DB.Exec("INSERT INTO task_configs VALUES(?,?,?)", job, uid, encrypted)
	return err
}

// Both the web form and automation API converge on the same worker inputs.
func (s *Server) prepareJob(w http.ResponseWriter, r *http.Request, c PersonalConfig) (PersonalConfig, string, bool) {
	parts := strings.Split(r.URL.Path, "/")
	revision := len(parts) == 5 && parts[1] == "api" && parts[2] == "jobs" && parts[4] == "revisions"
	if r.Method != "POST" || (r.URL.Path != "/api/jobs" && r.URL.Path != "/api/edits" && !revision) {
		return c, "", true
	}
	var override *PersonalConfig
	if r.URL.Path == "/api/jobs" && strings.HasPrefix(r.Header.Get("Content-Type"), "application/json") {
		var d struct {
			Prompt        string          `json:"prompt"`
			TemplateID    string          `json:"template_id"`
			Style         string          `json:"style"`
			Duration      int             `json:"duration"`
			Orientation   string          `json:"orientation"`
			AutoApprove   bool            `json:"auto_approve"`
			ReferenceURLs []string        `json:"reference_urls"`
			SourceIDs     []string        `json:"source_ids"`
			BGMEnabled    bool            `json:"bgm_enabled"`
			BGMTrackID    string          `json:"bgm_track_id"`
			BGMUploadID   string          `json:"bgm_upload_id"`
			BGMVolume     *float64        `json:"bgm_volume"`
			Config        *PersonalConfig `json:"config"`
		}
		if !decode(w, r, &d) {
			return c, "", false
		}
		if d.Duration == 0 {
			d.Duration = 30
		}
		if d.Orientation == "" {
			d.Orientation = "landscape"
		}
		if d.Style == "" {
			d.Style = "studio_noir"
		}
		sourceIDs, _ := json.Marshal(d.SourceIDs)
		form := url.Values{"template_id": {d.TemplateID}, "prompt": {d.Prompt}, "style": {d.Style}, "duration": {strconv.Itoa(d.Duration)}, "orientation": {d.Orientation}, "auto_approve": {strconv.FormatBool(d.AutoApprove)}, "reference_urls": {strings.Join(d.ReferenceURLs, "\n")}, "source_ids": {string(sourceIDs)}}
		form.Set("bgm_enabled", strconv.FormatBool(d.BGMEnabled))
		form.Set("bgm_track_id", d.BGMTrackID)
		form.Set("bgm_upload_id", d.BGMUploadID)
		if d.BGMVolume != nil {
			form.Set("bgm_volume", strconv.FormatFloat(*d.BGMVolume, 'f', -1, 64))
		}
		if len(d.SourceIDs) == 0 {
			form.Set("source_ids", "[]")
		}
		body := form.Encode()
		r.Body = readCloser(body)
		r.ContentLength = int64(len(body))
		r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		override = d.Config
	} else {
		// Multipart bodies stay streaming. The normal web flow uses saved personal settings;
		// API callers can configure the account or submit JSON with a per-task config.
	}
	if override != nil {
		if err := normalizeConfig(override, c); err != nil {
			fail(w, 422, err.Error())
			return c, "", false
		}
		c = *override
	}
	if !c.Saved && !c.UsePlatform && c.Text.APIKey == "" && c.Text.Model == "" && c.Text.BaseURL == "" {
		catalog, e := s.Store.catalog()
		if e == nil && len(catalog.Models) > 0 && s.Billing.Enabled {
			c.UsePlatform = true
		}
	}
	var err error
	c, err = s.effective(c)
	if err != nil {
		fail(w, 400, err.Error())
		return c, "", false
	}
	if err = s.platformAdmission(current(r).ID, c); err != nil {
		fail(w, 402, err.Error())
		return c, "", false
	}
	public := c.public()
	if !public.TextReady || !public.VisionReady || ((r.URL.Path == "/api/jobs" || revision) && !public.SpeechReady) {
		fail(w, 400, "请先完善 API 配置，或在请求 config 中传入完整配置。")
		return c, "", false
	}
	job := randomID(6)
	if err := s.Store.saveTaskConfig(current(r).ID, job, c); err != nil {
		s.internal(w, err)
		return c, "", false
	}
	return c, job, true
}

type stringReadCloser struct{ *strings.Reader }

func (s stringReadCloser) Close() error        { return nil }
func readCloser(value string) stringReadCloser { return stringReadCloser{strings.NewReader(value)} }
func bearerAllowed(path string) bool {
	if path == "/api/music/uploads" || strings.HasPrefix(path, "/api/music/uploads/") {
		return true
	}
	return path == "/api/usage" || path == "/api/billing" || path == "/api/wallet" || path == "/api/wallet/ledger" || path == "/api/edits" || strings.HasPrefix(path, "/api/edits/") || path == "/api/config" || path == "/api/config/models" || path == "/api/jobs" || strings.HasPrefix(path, "/api/jobs/") || path == "/api/styles" || path == "/api/sources" || strings.HasPrefix(path, "/api/sources/") || path == "/api/voices" || strings.HasPrefix(path, "/api/voices/")
}
