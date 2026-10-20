package main

import (
	"crypto/rand"
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"
	"unicode/utf8"
)

// Platform credentials are encrypted; public choices carry only labels and prices.
type PlatformModel struct {
	ID      string  `json:"id"`
	Label   string  `json:"label"`
	Role    string  `json:"role"`
	Enabled bool    `json:"enabled"`
	Channel Channel `json:"channel"`
	Price   Rate    `json:"price"`
}
type PlatformCatalog struct {
	Models        []PlatformModel `json:"models"`
	DefaultText   string          `json:"default_text"`
	DefaultVision string          `json:"default_vision"`
	RechargeHelp  string          `json:"recharge_help"`
	Revision      int64           `json:"revision"`
}

func (s *Store) initPlatform() error {
	_, err := s.DB.Exec(`CREATE TABLE IF NOT EXISTS platform_settings(id INTEGER PRIMARY KEY CHECK(id=1),ciphertext BLOB NOT NULL);
 CREATE TABLE IF NOT EXISTS admin_audit(id TEXT PRIMARY KEY,actor_id TEXT NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL,created_at INTEGER NOT NULL);`)
	return err
}
func (s *Store) catalog() (PlatformCatalog, error) {
	c := PlatformCatalog{Models: []PlatformModel{}, RechargeHelp: "请联系网站管理员，确认付款后由管理员入账。首次充值至少 5 元。"}
	var raw []byte
	err := s.DB.QueryRow("SELECT ciphertext FROM platform_settings WHERE id=1").Scan(&raw)
	if errors.Is(err, sql.ErrNoRows) {
		return c, nil
	}
	if err != nil {
		return c, err
	}
	n := s.Cipher.NonceSize()
	if len(raw) < n {
		return c, errors.New("invalid platform settings")
	}
	plain, err := s.Cipher.Open(nil, raw[:n], raw[n:], []byte("platform-catalog"))
	if err != nil {
		return c, err
	}
	err = json.Unmarshal(plain, &c)
	return c, err
}
func (c PlatformCatalog) model(id, role string) (PlatformModel, error) {
	if id == "" {
		if role == "text" {
			id = c.DefaultText
		} else {
			id = c.DefaultVision
		}
	}
	for _, m := range c.Models {
		if m.ID == id && m.Role == role && m.Enabled {
			return m, nil
		}
	}
	return PlatformModel{}, errors.New("所选平台模型不可用，请在模型配置中重新选择。")
}
func (c PlatformCatalog) public(admin bool) PlatformCatalog {
	out := c
	out.Models = []PlatformModel{}
	for _, m := range c.Models {
		if !admin && !m.Enabled {
			continue
		}
		m.Channel.KeyConfigured = m.Channel.APIKey != ""
		m.Channel.APIKey = ""
		m.Channel.ClearKey = false
		if !admin {
			m.Channel = Channel{Model: m.Channel.Model}
		}
		out.Models = append(out.Models, m)
	}
	return out
}
func (s *Store) saveCatalog(c PlatformCatalog, actor string) error {
	raw, err := json.Marshal(c)
	if err != nil {
		return err
	}
	nonce := make([]byte, s.Cipher.NonceSize())
	if _, err = rand.Read(nonce); err != nil {
		return err
	}
	encrypted := s.Cipher.Seal(nonce, nonce, raw, []byte("platform-catalog"))
	tx, err := s.DB.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err = tx.Exec("INSERT INTO platform_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET ciphertext=excluded.ciphertext", encrypted); err != nil {
		return err
	}
	audit, _ := json.Marshal(c.public(true))
	if _, err = tx.Exec("INSERT INTO admin_audit VALUES(?,?,?,?,?)", randomID(16), actor, "platform.update", string(audit), time.Now().Unix()); err != nil {
		return err
	}
	return tx.Commit()
}
func (s *Server) platformAdmin(w http.ResponseWriter, r *http.Request) {
	if !requireAdmin(w, r) {
		return
	}
	s.ConfigMu.Lock()
	defer s.ConfigMu.Unlock()
	old, err := s.Store.catalog()
	if err != nil {
		s.internal(w, err)
		return
	}
	if r.Method == "GET" {
		reply(w, 200, old.public(true))
		return
	}
	var c PlatformCatalog
	if !decode(w, r, &c) {
		return
	}
	if c.Revision != old.Revision {
		fail(w, 409, "模型设置已被更新，请刷新后再保存。")
		return
	}
	if len(c.Models) > 40 || len(c.RechargeHelp) > 1500 {
		fail(w, 422, "最多配置40个模型，充值说明最多1500字节。")
		return
	}
	seen := map[string]bool{}
	for i := range c.Models {
		m := &c.Models[i]
		m.Label = strings.TrimSpace(m.Label)
		if !requestPattern.MatchString(m.ID) || seen[m.ID] || (m.Role != "text" && m.Role != "vision") || m.Label == "" || utf8.RuneCountInString(m.Label) > 70 {
			fail(w, 422, "请检查模型标识、名称和用途。")
			return
		}
		seen[m.ID] = true
		previous := defaultConfig()
		next := defaultConfig()
		for _, p := range old.Models {
			if p.ID == m.ID {
				previous.Text = p.Channel
			}
		}
		next.Text = m.Channel
		if next.Text.Protocol == "" {
			next.Text.Protocol = "chat_completions"
		}
		if err = normalizeConfig(&next, previous); err != nil {
			fail(w, 422, err.Error())
			return
		}
		m.Channel = next.Text
		if len(m.Channel.Fallbacks) > 0 {
			fail(w, 422, "平台模型请分别添加；不使用未定价的备用模型。")
			return
		}
		p := &m.Price
		if len([]rune(p.Note)) > 300 {
			fail(w, 422, "价格说明最多300字。")
			return
		}
		p.Model = m.Channel.Model
		if p.MaxInput < 1024 || p.MaxInput > 1000000 || p.Input <= 0 || p.Output <= 0 || p.Cached < 0 || p.Cached > p.Input || p.Input > 10000000000 || p.Output > 10000000000 || m.Channel.MaxTokens < 1 {
			fail(w, 422, "请填写有效的输入、输出、缓存价格和模型上限。")
			return
		}
		if m.Enabled && (m.Channel.APIKey == "" || m.Channel.Model == "" || m.Channel.BaseURL == "") {
			fail(w, 422, "启用模型前请填写地址、密钥和模型名称。")
			return
		}
	}
	if c.DefaultText != "" {
		if _, err = c.model(c.DefaultText, "text"); err != nil {
			fail(w, 422, "默认生成模型需为已启用模型，也可以暂时留空。")
			return
		}
	}
	if c.DefaultVision != "" {
		if _, err = c.model(c.DefaultVision, "vision"); err != nil {
			fail(w, 422, "默认审核模型需为已启用模型，也可以暂时留空。")
			return
		}
	}
	c.Revision = old.Revision + 1
	if err = s.Store.saveCatalog(c, current(r).ID); err != nil {
		s.internal(w, err)
		return
	}
	reply(w, 200, c.public(true))
}
func (s *Server) platformModels(w http.ResponseWriter, r *http.Request) {
	if !requireAdmin(w, r) {
		return
	}
	c, err := s.Store.catalog()
	if err != nil {
		s.internal(w, err)
		return
	}
	var d struct {
		ID string `json:"id"`
	}
	if !decode(w, r, &d) {
		return
	}
	for _, m := range c.Models {
		if m.ID == d.ID {
			s.fetchModels(w, r, m.Channel)
			return
		}
	}
	fail(w, 404, "请先保存模型服务，再获取模型列表。")
}
func (s *Server) createManagedUser(w http.ResponseWriter, r *http.Request) {
	if !requireAdmin(w, r) {
		return
	}
	var d loginInput
	if !decode(w, r, &d) {
		return
	}
	d.Username = strings.ToLower(strings.TrimSpace(d.Username))
	d.DisplayName = strings.TrimSpace(d.DisplayName)
	if !usernamePattern.MatchString(d.Username) || utf8.RuneCountInString(d.Password) < 10 || len(d.Password) > 72 || utf8.RuneCountInString(d.DisplayName) > 60 {
		fail(w, 422, "账号需3至80位，密码至少10位且最多72字节。")
		return
	}
	u, err := s.Store.createUser(d.Username, d.Password, d.DisplayName, "user")
	if duplicate(err) {
		fail(w, 409, "账号已存在。")
		return
	}
	if err != nil {
		s.internal(w, err)
		return
	}
	s.Store.DB.Exec("INSERT INTO admin_audit VALUES(?,?,?,?,?)", randomID(16), current(r).ID, "user.create", u.ID, time.Now().Unix())
	reply(w, 201, u)
}

// A cumulative paid deposit opens platform access; consuming it does not reset the gate.
func (s *Store) prepaid(uid string) (bool, error) {
	var deposited int64
	err := s.DB.QueryRow("SELECT COALESCE(sum(amount_cents),0) FROM ledger WHERE user_id=? AND request_id NOT LIKE 'usage-%'", uid).Scan(&deposited)
	return deposited >= 500, err
}
func (s *Server) platformAdmission(uid string, c PersonalConfig) error {
	if !c.UsePlatform {
		return nil
	}
	ok, err := s.Store.prepaid(uid)
	if err != nil {
		return err
	}
	if !ok {
		return errors.New("使用平台模型需先充值 5 元；也可以配置自己的 API Key。")
	}
	u, err := s.Store.user(uid)
	if err != nil {
		return err
	}
	var held int64
	if err = s.Store.DB.QueryRow("SELECT COALESCE(sum(reserved_cents),0) FROM billing_calls WHERE user_id=? AND status IN ('reserved','unmetered')", uid).Scan(&held); err != nil {
		return err
	}
	if u.Balance-held <= 0 {
		return errors.New("可用余额已用完，请到余额与账单充值后继续。")
	}
	return nil
}
