package main

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"database/sql"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
	"unicode/utf8"

	"golang.org/x/crypto/bcrypt"
)

const cookieName = "frame_session"
const sessionSeconds = 7 * 86400

var usernamePattern = regexp.MustCompile(`^[a-z0-9][a-z0-9_.@+\-]{2,79}$`)
var requestPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{16,80}$`)

type userKey struct{}
type Server struct {
	CookieName   string
	Billing      *Billing
	Store        *Store
	Origins      map[string]bool
	Mux          *http.ServeMux
	Proxy        *httputil.ReverseProxy
	Dummy        []byte
	ConfigMu     sync.Mutex
	ModelsClient *http.Client
}

func reply(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(value)
}
func fail(w http.ResponseWriter, status int, message string) {
	reply(w, status, map[string]string{"detail": message})
}
func decode(w http.ResponseWriter, r *http.Request, v any) bool {
	r.Body = http.MaxBytesReader(w, r.Body, 32*1024)
	d := json.NewDecoder(r.Body)
	if err := d.Decode(v); err != nil {
		fail(w, 422, "请求格式不正确，请检查输入。")
		return false
	}
	if err := d.Decode(new(any)); err != io.EOF {
		fail(w, 422, "请求只能包含一个 JSON 对象。")
		return false
	}
	return true
}
func current(r *http.Request) User { return r.Context().Value(userKey{}).(User) }
func requireAdmin(w http.ResponseWriter, r *http.Request) bool {
	if current(r).Role != "admin" {
		fail(w, 403, "需要管理员权限。")
		return false
	}
	return true
}
func (s *Server) internal(w http.ResponseWriter, err error) {
	log.Printf("request failed: %T", err)
	fail(w, 500, "服务暂时不可用，请稍后重试。")
}
func clientIP(r *http.Request) string {
	host, _, _ := net.SplitHostPort(r.RemoteAddr)
	// Only the loopback Nginx proxy is trusted to supply this header.
	if ip := net.ParseIP(host); ip != nil && ip.IsLoopback() {
		if forwarded := net.ParseIP(r.Header.Get("X-Real-IP")); forwarded != nil {
			return forwarded.String()
		}
	}
	return host
}
func secureRequest(r *http.Request) bool {
	if r.TLS != nil {
		return true
	}
	host, _, _ := net.SplitHostPort(r.RemoteAddr)
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback() && r.Header.Get("X-Forwarded-Proto") == "https"
}
func (s *Server) session(w http.ResponseWriter, r *http.Request, u User) error {
	token := randomID(32)
	now := time.Now().Unix()
	agent := r.UserAgent()
	if len(agent) > 250 {
		agent = agent[:250]
	}
	tx, err := s.Store.DB.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err = tx.Exec("DELETE FROM sessions WHERE expires_at<?", now); err != nil {
		return err
	}
	if _, err = tx.Exec("INSERT INTO sessions VALUES(?,?,?,?,?,?)", randomID(16), u.ID, hashToken(token), now, now+sessionSeconds, agent); err != nil {
		return err
	}
	if err = tx.Commit(); err != nil {
		return err
	}
	http.SetCookie(w, &http.Cookie{Name: s.CookieName, Value: token, Path: "/", MaxAge: sessionSeconds, HttpOnly: true, Secure: secureRequest(r), SameSite: http.SameSiteLaxMode})
	return nil
}
func newServer(store *Store, dist, workerSocket string, origins []string) (*Server, error) {
	dummy, _ := bcrypt.GenerateFromPassword([]byte(randomID(32)), bcrypt.DefaultCost)
	s := &Server{CookieName: cookieName, Store: store, Origins: map[string]bool{}, Mux: http.NewServeMux(), Dummy: dummy}
	for _, o := range origins {
		s.Origins[strings.TrimRight(strings.TrimSpace(o), "/")] = true
	}
	target, _ := url.Parse("http://worker")
	proxy := httputil.NewSingleHostReverseProxy(target)
	proxy.Transport = &http.Transport{DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
		return (&net.Dialer{Timeout: 5 * time.Second}).DialContext(ctx, "unix", workerSocket)
	}, ResponseHeaderTimeout: 5 * time.Minute, MaxIdleConns: 10}
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		fail(w, 503, "视频服务正在启动，请稍后重试。")
	}
	s.Proxy = proxy
	s.ModelsClient = publicModelClient()
	var err error
	s.Billing, err = newBilling(store, filepath.Dir(store.Dir))
	if err != nil {
		return nil, err
	}
	m := s.Mux
	m.HandleFunc("GET /api/billing", s.billingInfo)
	m.HandleFunc("POST /api/auth/register", s.register)
	m.HandleFunc("POST /api/auth/login", s.login)
	m.HandleFunc("GET /api/auth/me", func(w http.ResponseWriter, r *http.Request) { reply(w, 200, current(r)) })
	m.HandleFunc("POST /api/auth/logout", s.logout)
	m.HandleFunc("PUT /api/auth/password", s.password)
	m.HandleFunc("GET /api/api-keys", s.apiKeys)
	m.HandleFunc("POST /api/api-keys", s.apiKeys)
	m.HandleFunc("DELETE /api/api-keys/{id}", s.revokeAPIKey)
	m.HandleFunc("GET /api/auth/sessions", s.sessions)
	m.HandleFunc("DELETE /api/auth/sessions/{id}", s.revoke)
	m.HandleFunc("GET /api/config", s.getConfig)
	m.HandleFunc("POST /api/config", s.setConfig)
	m.HandleFunc("POST /api/config/models", s.listModels)
	m.HandleFunc("GET /api/wallet", s.wallet)
	m.HandleFunc("GET /api/admin/users", s.users)
	m.HandleFunc("PATCH /api/admin/users/{id}", s.status)
	m.HandleFunc("POST /api/admin/users/{id}/credit", s.credit)
	m.HandleFunc("GET /api/admin/users/{id}/ledger", s.ledger)
	for _, pattern := range []string{"/api/jobs", "/api/jobs/", "/api/edits", "/api/edits/", "/api/styles", "/api/sources", "/api/sources/", "/api/voices", "/api/voices/"} {
		m.HandleFunc(pattern, s.worker)
	}
	m.HandleFunc("/api/", func(w http.ResponseWriter, r *http.Request) { fail(w, 404, "接口不存在。") })
	files := http.FileServer(http.Dir(dist))
	m.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "..") || strings.HasPrefix(r.URL.Path, "/.") {
			http.NotFound(w, r)
			return
		}
		if _, err := os.Stat(filepath.Join(dist, filepath.Clean("/"+r.URL.Path))); err != nil && r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		files.ServeHTTP(w, r)
	})
	return s, nil
}
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if strings.HasPrefix(r.URL.Path, "/internal/") {
		s.internalMeter(w, r)
		return
	}
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("Referrer-Policy", "strict-origin-when-cross-origin")
	w.Header().Set("X-Frame-Options", "SAMEORIGIN")
	w.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'")
	if strings.HasPrefix(r.URL.Path, "/api/") {
		w.Header().Set("Cache-Control", "no-store")
		if r.Method != "GET" && r.Method != "HEAD" && r.Method != "OPTIONS" {
			origin := r.Header.Get("Origin")
			if (origin != "" && !s.Origins[origin]) || r.Header.Get("Sec-Fetch-Site") == "cross-site" || (r.Header.Get("X-Frame-Request") != "1" && !(strings.HasPrefix(r.Header.Get("Authorization"), "Bearer ") && bearerAllowed(r.URL.Path))) {
				fail(w, 403, "请求校验失败，请从站内页面重试。")
				return
			}
		}
		if r.URL.Path != "/api/auth/register" && r.URL.Path != "/api/auth/login" {
			var u User
			var err error
			if authorization := r.Header.Get("Authorization"); strings.HasPrefix(authorization, "Bearer ") {
				if !bearerAllowed(r.URL.Path) {
					fail(w, 403, "此接口仅支持在网页内操作。")
					return
				}
				u, err = s.Store.tokenUser(strings.TrimPrefix(authorization, "Bearer "))
			} else {
				var cookie *http.Cookie
				cookie, err = r.Cookie(s.CookieName)
				if err == nil {
					u, err = s.Store.authenticate(cookie.Value)
				}
			}
			if err != nil {
				fail(w, 401, "登录或调用密钥无效，请重新登录或检查密钥。")
				return
			}
			r = r.WithContext(context.WithValue(r.Context(), userKey{}, u))
		}
	}
	s.Mux.ServeHTTP(w, r)
}

type loginInput struct {
	Username    string `json:"username"`
	Password    string `json:"password"`
	DisplayName string `json:"display_name"`
}

func (s *Server) register(w http.ResponseWriter, r *http.Request) {
	if err := s.Store.limit("register:"+clientIP(r), 5, 3600); err != nil {
		fail(w, 429, err.Error())
		return
	}
	var d loginInput
	if !decode(w, r, &d) {
		return
	}
	d.Username = strings.ToLower(strings.TrimSpace(d.Username))
	d.DisplayName = strings.TrimSpace(d.DisplayName)
	if !usernamePattern.MatchString(d.Username) || utf8.RuneCountInString(d.Password) < 10 || len(d.Password) > 72 || utf8.RuneCountInString(d.DisplayName) > 60 {
		fail(w, 422, "账号需为3至80位字母、数字或邮箱格式；密码至少10位且最多72字节。")
		return
	}
	u, err := s.Store.createUser(d.Username, d.Password, d.DisplayName, "user")
	if duplicate(err) {
		fail(w, 409, "账号已被注册。")
		return
	}
	if err != nil {
		s.internal(w, err)
		return
	}
	if err = s.session(w, r, u); err != nil {
		s.internal(w, err)
		return
	}
	reply(w, 201, u)
}
func (s *Server) login(w http.ResponseWriter, r *http.Request) {
	if err := s.Store.limit("login:"+clientIP(r), 30, 900); err != nil {
		fail(w, 429, err.Error())
		return
	}
	var d loginInput
	if !decode(w, r, &d) {
		return
	}
	d.Username = strings.ToLower(strings.TrimSpace(d.Username))
	if len(d.Username) > 80 || len(d.Password) > 72 {
		fail(w, 401, "账号或密码错误。")
		return
	}
	if err := s.Store.limit("login-user:"+d.Username, 15, 900); err != nil {
		fail(w, 429, err.Error())
		return
	}
	u, err := scanUser(s.Store.DB.QueryRow("SELECT "+userFields+" FROM users WHERE username=?", d.Username))
	hash := s.Dummy
	if err == nil {
		hash = []byte(u.Password)
	}
	valid := bcrypt.CompareHashAndPassword(hash, []byte(d.Password)) == nil
	if err != nil || !valid || !u.Active {
		fail(w, 401, "账号或密码错误，或账号已被停用。")
		return
	}
	if err = s.session(w, r, u); err != nil {
		s.internal(w, err)
		return
	}
	reply(w, 200, u)
}
func (s *Server) logout(w http.ResponseWriter, r *http.Request) {
	if _, err := s.Store.DB.Exec("DELETE FROM sessions WHERE id=?", current(r).SessionID); err != nil {
		s.internal(w, err)
		return
	}
	http.SetCookie(w, &http.Cookie{Name: s.CookieName, Value: "", Path: "/", MaxAge: -1, HttpOnly: true, Secure: secureRequest(r), SameSite: http.SameSiteLaxMode})
	reply(w, 200, map[string]bool{"ok": true})
}
func (s *Server) sessions(w http.ResponseWriter, r *http.Request) {
	rows, err := s.Store.DB.Query("SELECT id,created_at,expires_at,agent FROM sessions WHERE user_id=? AND expires_at>? ORDER BY created_at DESC", current(r).ID, time.Now().Unix())
	if err != nil {
		s.internal(w, err)
		return
	}
	defer rows.Close()
	items := []map[string]any{}
	for rows.Next() {
		var id, agent string
		var created, expires int64
		if err = rows.Scan(&id, &created, &expires, &agent); err != nil {
			s.internal(w, err)
			return
		}
		items = append(items, map[string]any{"id": id, "agent": agent, "created_at": created, "expires_at": expires, "current": id == current(r).SessionID})
	}
	reply(w, 200, items)
}
func (s *Server) revoke(w http.ResponseWriter, r *http.Request) {
	if _, err := s.Store.DB.Exec("DELETE FROM sessions WHERE id=? AND user_id=?", r.PathValue("id"), current(r).ID); err != nil {
		s.internal(w, err)
		return
	}
	reply(w, 200, map[string]bool{"ok": true})
}
func (s *Server) password(w http.ResponseWriter, r *http.Request) {
	u := current(r)
	if err := s.Store.limit("password:"+u.ID, 15, 900); err != nil {
		fail(w, 429, err.Error())
		return
	}
	var d struct {
		Current string `json:"current_password"`
		New     string `json:"new_password"`
	}
	if !decode(w, r, &d) {
		return
	}
	if len(d.Current) > 72 || utf8.RuneCountInString(d.New) < 10 || len(d.New) > 72 {
		fail(w, 422, "新密码至少10位且最多72字节。")
		return
	}
	if bcrypt.CompareHashAndPassword([]byte(u.Password), []byte(d.Current)) != nil {
		fail(w, 400, "当前密码错误。")
		return
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(d.New), bcrypt.DefaultCost)
	if err != nil {
		s.internal(w, err)
		return
	}
	tx, err := s.Store.DB.Begin()
	if err != nil {
		s.internal(w, err)
		return
	}
	defer tx.Rollback()
	res, err := tx.Exec("UPDATE users SET password=? WHERE id=? AND password=?", string(hash), u.ID, u.Password)
	if err != nil {
		s.internal(w, err)
		return
	}
	n, _ := res.RowsAffected()
	if n != 1 {
		fail(w, 409, "密码已更新，请重新登录。")
		return
	}
	if _, err = tx.Exec("DELETE FROM sessions WHERE user_id=?", u.ID); err != nil {
		s.internal(w, err)
		return
	}
	if err = tx.Commit(); err != nil {
		s.internal(w, err)
		return
	}
	if err = s.session(w, r, u); err != nil {
		s.internal(w, err)
		return
	}
	reply(w, 200, map[string]bool{"ok": true})
}
func (s *Server) getConfig(w http.ResponseWriter, r *http.Request) {
	c, err := s.Store.config(current(r).ID)
	if err != nil {
		s.internal(w, err)
		return
	}
	visible := c.public()
	effective, e := s.effective(c)
	if e == nil && c.UsePlatform {
		ready := effective.public()
		visible.TextReady = ready.TextReady
		visible.VisionReady = ready.VisionReady
		visible.SpeechReady = ready.SpeechReady
	}
	reply(w, 200, visible)
}
func (s *Server) setConfig(w http.ResponseWriter, r *http.Request) {
	var c PersonalConfig
	if !decode(w, r, &c) {
		return
	}
	s.ConfigMu.Lock()
	defer s.ConfigMu.Unlock()
	old, err := s.Store.config(current(r).ID)
	if err != nil {
		s.internal(w, err)
		return
	}
	if err = normalizeConfig(&c, old); err != nil {
		fail(w, 422, err.Error())
		return
	}
	if err = s.Store.saveConfig(current(r).ID, c); err != nil {
		s.internal(w, err)
		return
	}
	s.getConfig(w, r)
}
func (s *Server) wallet(w http.ResponseWriter, r *http.Request) {
	items, err := s.Store.ledger(current(r).ID)
	if err != nil {
		s.internal(w, err)
		return
	}
	u, err := s.Store.user(current(r).ID)
	if err != nil {
		s.internal(w, err)
		return
	}
	reply(w, 200, map[string]any{"balance_cents": u.Balance, "entries": items, "billing_enabled": s.Billing.Enabled, "currency": "CNY"})
}
func (s *Server) users(w http.ResponseWriter, r *http.Request) {
	if !requireAdmin(w, r) {
		return
	}
	offset, _ := strconv.Atoi(r.URL.Query().Get("offset"))
	if offset < 0 {
		offset = 0
	}
	rows, err := s.Store.DB.Query("SELECT "+userFields+" FROM users ORDER BY created_at DESC,id LIMIT 100 OFFSET ?", offset)
	if err != nil {
		s.internal(w, err)
		return
	}
	items := []User{}
	for rows.Next() {
		u, err := scanUser(rows)
		if err != nil {
			rows.Close()
			s.internal(w, err)
			return
		}
		items = append(items, u)
	}
	rows.Close()
	var total int
	if err = s.Store.DB.QueryRow("SELECT count(*) FROM users").Scan(&total); err != nil {
		s.internal(w, err)
		return
	}
	reply(w, 200, map[string]any{"items": items, "total": total})
}
func (s *Server) status(w http.ResponseWriter, r *http.Request) {
	if !requireAdmin(w, r) {
		return
	}
	var d struct {
		Active *bool `json:"active"`
	}
	if !decode(w, r, &d) {
		return
	}
	if d.Active == nil {
		fail(w, 422, "请选择账户状态。")
		return
	}
	u, err := s.Store.user(r.PathValue("id"))
	if err != nil {
		fail(w, 404, "用户不存在。")
		return
	}
	if u.Role == "admin" {
		fail(w, 400, "管理员账号不可在此停用。")
		return
	}
	tx, err := s.Store.DB.Begin()
	if err != nil {
		s.internal(w, err)
		return
	}
	defer tx.Rollback()
	if _, err = tx.Exec("UPDATE users SET active=? WHERE id=?", *d.Active, u.ID); err != nil {
		s.internal(w, err)
		return
	}
	if !*d.Active {
		if _, err = tx.Exec("DELETE FROM sessions WHERE user_id=?", u.ID); err != nil {
			s.internal(w, err)
			return
		}
	}
	if err = tx.Commit(); err != nil {
		s.internal(w, err)
		return
	}
	u.Active = *d.Active
	reply(w, 200, u)
}
func (s *Server) credit(w http.ResponseWriter, r *http.Request) {
	if !requireAdmin(w, r) {
		return
	}
	var d struct {
		Amount    int64  `json:"amount_cents"`
		Note      string `json:"note"`
		RequestID string `json:"request_id"`
	}
	if !decode(w, r, &d) {
		return
	}
	d.Note = strings.TrimSpace(d.Note)
	if d.Amount <= 0 || d.Amount > 100000000 || utf8.RuneCountInString(d.Note) < 2 || utf8.RuneCountInString(d.Note) > 200 || !requestPattern.MatchString(d.RequestID) {
		fail(w, 422, "请检查充值金额、备注和操作凭证。")
		return
	}
	entry, err := s.Store.credit(current(r).ID, r.PathValue("id"), d.Amount, d.Note, d.RequestID)
	if err != nil {
		fail(w, 409, "充值未完成：请检查用户、金额及重复操作凭证。")
		return
	}
	reply(w, 200, entry)
}
func (s *Server) ledger(w http.ResponseWriter, r *http.Request) {
	if !requireAdmin(w, r) {
		return
	}
	items, err := s.Store.ledger(r.PathValue("id"))
	if err != nil {
		s.internal(w, err)
		return
	}
	reply(w, 200, items)
}
func (s *Server) worker(w http.ResponseWriter, r *http.Request) {
	u := current(r)
	if (r.Method != "GET" && (strings.HasPrefix(r.URL.Path, "/api/sources") || strings.HasPrefix(r.URL.Path, "/api/edits") || strings.HasPrefix(r.URL.Path, "/api/jobs/"))) || strings.HasPrefix(r.URL.Path, "/api/voices/") {
		if err := s.Store.limit("sources:"+u.ID, 30, 60); err != nil {
			fail(w, 429, err.Error())
			return
		}
	}
	c, err := s.Store.config(u.ID)
	if err != nil {
		s.internal(w, err)
		return
	}
	if strings.HasPrefix(r.URL.Path, "/api/jobs/") || strings.HasPrefix(r.URL.Path, "/api/edits/") {
		parts := strings.Split(r.URL.Path, "/")
		if len(parts) > 3 {
			frozen, e := s.Store.taskConfig(u.ID, parts[3])
			if e == nil {
				c = frozen
			} else if !errors.Is(e, sql.ErrNoRows) {
				s.internal(w, e)
				return
			}
		}
	}
	c, jobID, ok := s.prepareJob(w, r, c)
	if !ok {
		return
	}
	payload, err := json.Marshal(map[string]any{"user": map[string]string{"id": u.ID}, "config": c, "job_id": jobID, "admin_id": s.Store.adminID(), "time": time.Now().Unix()})
	if err != nil {
		s.internal(w, err)
		return
	}
	encoded := base64.RawURLEncoding.EncodeToString(payload)
	mac := hmac.New(sha256.New, s.Store.WorkerKey)
	mac.Write([]byte(r.Method + "\n" + r.URL.RequestURI() + "\n" + encoded))
	r.Header.Del("Authorization")
	r.Header.Del("Cookie")
	r.Header.Set("X-Frame-Context", encoded)
	r.Header.Set("X-Frame-Signature", hex.EncodeToString(mac.Sum(nil)))
	limit := int64(510 * 1024 * 1024)
	if strings.HasPrefix(r.URL.Path, "/api/edits/") || strings.HasPrefix(r.URL.Path, "/api/jobs/") {
		limit = 256 * 1024
	}
	r.Body = http.MaxBytesReader(w, r.Body, limit)
	s.Proxy.ServeHTTP(w, r)
}
