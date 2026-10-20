package main

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// Prices are integer micro-yuan per million tokens. No floating-point money or group multipliers.
type Rate struct {
	Note     string `json:"note,omitempty"`
	Model    string `json:"model"`
	Role     string `json:"role,omitempty"`
	Revision int64  `json:"revision,omitempty"`
	Input    int64  `json:"input_micro_per_million"`
	Output   int64  `json:"output_micro_per_million"`
	Cached   int64  `json:"cached_micro_per_million"`
	MaxInput int64  `json:"max_input_tokens"`
	Offpeak  bool   `json:"offpeak_half"`
}
type PriceBook struct {
	Currency       string `json:"currency"`
	VerifiedAt     string `json:"verified_at"`
	Source         string `json:"source"`
	CacheSource    string `json:"cache_source"`
	EndpointSuffix string `json:"endpoint_suffix"`
	Rates          []Rate `json:"rates"`
}
type Billing struct {
	Enabled    bool
	ChargeBYOK bool
	Prices     PriceBook
	Store      *Store
}

func newBilling(store *Store, root string) (*Billing, error) {
	b := &Billing{Store: store, Enabled: os.Getenv("C2V_BILLING_ENABLED") == "true", ChargeBYOK: false}
	raw, err := os.ReadFile(filepath.Join(root, "api/pricing/official-20261019.json"))
	if err == nil {
		err = json.Unmarshal(raw, &b.Prices)
	}
	if err != nil && b.Enabled {
		return nil, err
	}
	_, err = store.DB.Exec(`CREATE TABLE IF NOT EXISTS billing_calls(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),job_id TEXT NOT NULL,model TEXT NOT NULL,role TEXT NOT NULL,price TEXT NOT NULL,reserved_cents INTEGER NOT NULL,cost_micro INTEGER NOT NULL DEFAULT 0,charged_cents INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL,usage TEXT NOT NULL DEFAULT '{}',created_at INTEGER NOT NULL);
 CREATE INDEX IF NOT EXISTS billing_calls_user ON billing_calls(user_id,status);`)
	if err == nil {
		err = b.migrateUsage()
	}
	return b, err
}
func (b *Billing) rate(model, endpoint string, at time.Time) (Rate, error) {
	u, err := url.Parse(endpoint)
	if err != nil || b.Prices.EndpointSuffix == "" || !strings.HasSuffix(u.Hostname(), b.Prices.EndpointSuffix) {
		return Rate{}, errors.New("此服务尚未核验官方价格，不能使用站内计费。")
	}
	for _, r := range b.Prices.Rates {
		if r.Model == model {
			if r.Offpeak {
				hour := (at.UTC().Hour() + 8) % 24
				if hour >= 22 || hour < 8 {
					r.Input /= 2
					r.Output /= 2
					r.Cached /= 2
				}
			}
			return r, nil
		}
	}
	return Rate{}, errors.New("模型缺少已核验的官方单价，请联系管理员。")
}
func ceil(n, d int64) int64 { return (n + d - 1) / d }
func tokenCost(r Rate, input, output, cached int64) (int64, error) {
	if input < 0 || output < 0 || cached < 0 || cached > input || input > r.MaxInput || output > 1000000 {
		return 0, errors.New("模型返回用量超出已核验计费范围。")
	}
	return ceil((input-cached)*r.Input+cached*r.Cached+output*r.Output, 1000000), nil
}

type meterRequest struct {
	AdminActor         string          `json:"-"`
	ReconciliationNote string          `json:"-"`
	ID                 string          `json:"id"`
	UserID             string          `json:"user_id"`
	JobID              string          `json:"job_id"`
	Model              string          `json:"model"`
	Role               string          `json:"role"`
	MaxOutput          int64           `json:"max_output"`
	InputBound         int64           `json:"input_bound"`
	DurationMS         int64           `json:"duration_ms"`
	FirstTokenMS       int64           `json:"first_token_ms"`
	ResponseID         string          `json:"response_id"`
	ErrorType          string          `json:"error_type"`
	Rejected           bool            `json:"rejected"`
	Stream             bool            `json:"stream"`
	Stage              string          `json:"stage"`
	Input              int64           `json:"input_tokens"`
	Output             int64           `json:"output_tokens"`
	Cached             int64           `json:"cached_input_tokens"`
	Metered            bool            `json:"metered"`
	Usage              json.RawMessage `json:"usage"`
}

func (b *Billing) authorize(d meterRequest) (map[string]any, error) {
	cfg, err := b.Store.taskConfig(d.UserID, d.JobID)
	if errors.Is(err, sql.ErrNoRows) {
		cfg, err = b.Store.config(d.UserID)
		if cfg.UsePlatform {
			return nil, errors.New("平台任务缺少固定配置，请重新创建任务。")
		}
	}
	if err != nil {
		return nil, err
	}
	// Personal API calls are settled by the user's provider, outside our ledger.
	if !cfg.UsePlatform {
		return map[string]any{"billing": false}, nil
	}
	paid := cfg.UsePlatform
	if paid && !b.Enabled {
		return nil, errors.New("平台计费已暂停，请稍后再试。")
	}
	ch := cfg.Text
	if d.Role == "vision" {
		ch = cfg.Vision
		if cfg.VisionInherit {
			ch = cfg.Text
		}
	} else if d.Role != "text" {
		return nil, errors.New("该调用类型不可计费。")
	}
	allowed := d.Model == ch.Model
	for _, fallback := range ch.Fallbacks {
		allowed = allowed || d.Model == fallback
	}
	if !allowed {
		return nil, errors.New("模型与任务配置不一致。")
	}
	rate := Rate{Model: d.Model, MaxInput: 1000000}
	if paid {
		found := false
		for _, p := range cfg.PlatformPrices {
			if p.Model == d.Model && (p.Role == "" || p.Role == d.Role) {
				rate = p
				found = true
				break
			}
		}
		if !found {
			rate, err = b.rate(d.Model, ch.BaseURL, time.Now())
		} else if rate.Offpeak {
			hour := (time.Now().UTC().Hour() + 8) % 24
			if hour >= 22 || hour < 8 {
				rate.Input /= 2
				rate.Output /= 2
				rate.Cached /= 2
			}
		}
		if err != nil {
			return nil, err
		}
		prepaid, e := b.Store.prepaid(d.UserID)
		if e != nil {
			return nil, e
		}
		if !prepaid {
			return nil, errors.New("使用平台模型需先充值 5 元，请前往余额与账单。")
		}
	}
	if d.MaxOutput <= 0 || d.MaxOutput > 1000000 {
		return nil, errors.New("输出上限无效。")
	}
	// UTF-8 bytes plus protocol overhead bound text tokenization; image calls reserve full context.
	bound := d.InputBound
	if bound <= 0 || bound > rate.MaxInput {
		bound = rate.MaxInput
	}
	maximum, err := tokenCost(rate, bound, d.MaxOutput, 0)
	if err != nil {
		return nil, err
	}
	reserved := ceil(maximum, 10000)
	mode := "byok"
	if paid {
		mode = "platform"
	}
	price, _ := json.Marshal(rate)
	tx, err := b.Store.DB.Begin()
	if err != nil {
		return nil, err
	}
	defer tx.Rollback()
	var previousUser, previousJob, status string
	var previousHold int64
	err = tx.QueryRow("SELECT user_id,job_id,status,reserved_cents FROM billing_calls WHERE id=?", d.ID).Scan(&previousUser, &previousJob, &status, &previousHold)
	if err == nil {
		if previousUser != d.UserID || previousJob != d.JobID {
			return nil, errors.New("计费凭证冲突。")
		}
		return map[string]any{"billing": true, "reserved_cents": previousHold, "status": status}, nil
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return nil, err
	}
	var balance, held int64
	var active bool
	if err = tx.QueryRow("SELECT balance_cents,active FROM users WHERE id=?", d.UserID).Scan(&balance, &active); err != nil || !active {
		return nil, errors.New("账户不可用。")
	}
	if err = tx.QueryRow("SELECT COALESCE(sum(reserved_cents),0) FROM billing_calls WHERE user_id=? AND status IN ('reserved','unmetered')", d.UserID).Scan(&held); err != nil {
		return nil, err
	}
	if balance-held < reserved {
		return nil, errors.New("可用余额不足以覆盖本次模型调用上限，请充值后继续。")
	}
	_, err = tx.Exec("INSERT INTO billing_calls(id,user_id,job_id,model,role,price,reserved_cents,status,created_at) VALUES(?,?,?,?,?,?,?,'reserved',?)", d.ID, d.UserID, d.JobID, d.Model, d.Role, string(price), reserved, time.Now().Unix())
	if err != nil {
		return nil, err
	}
	if _, err = tx.Exec("UPDATE billing_calls SET mode=?,stage=?,stream=? WHERE id=?", mode, truncate(d.Stage, 60), d.Stream, d.ID); err != nil {
		return nil, err
	}
	if err = tx.Commit(); err != nil {
		return nil, err
	}
	return map[string]any{"billing": paid, "reserved_cents": reserved}, nil
}
func (b *Billing) settle(d meterRequest) (map[string]any, error) {
	tx, err := b.Store.DB.Begin()
	if err != nil {
		return nil, err
	}
	defer tx.Rollback()
	var uid, job, price, status, mode string
	var reserve, charged int64
	err = tx.QueryRow("SELECT user_id,job_id,price,status,reserved_cents,charged_cents,mode FROM billing_calls WHERE id=?", d.ID).Scan(&uid, &job, &price, &status, &reserve, &charged, &mode)
	if errors.Is(err, sql.ErrNoRows) {
		return map[string]any{"billing": false}, nil
	}
	if err != nil {
		return nil, err
	}
	if uid != d.UserID || job != d.JobID {
		return nil, errors.New("计费凭证不属于此任务。")
	}
	// Older releases recorded zero-cost BYOK usage. Never settle those locally.
	if mode != "platform" {
		return map[string]any{"billing": false}, nil
	}
	if status == "settled" || status == "rejected" {
		return map[string]any{"billing": true, "charged_cents": charged}, nil
	}
	if d.AdminActor == "" {
		if _, err = tx.Exec("UPDATE billing_calls SET duration_ms=?,first_token_ms=?,response_id=?,actual_model=?,error_type=?,finished_at=? WHERE id=?", max(d.DurationMS, 0), max(d.FirstTokenMS, 0), truncate(d.ResponseID, 200), truncate(d.Model, 150), truncate(d.ErrorType, 80), time.Now().Unix(), d.ID); err != nil {
			return nil, err
		}
	}
	if d.Rejected && !d.Metered {
		if _, err = tx.Exec("UPDATE billing_calls SET status='rejected',reserved_cents=0 WHERE id=?", d.ID); err != nil {
			return nil, err
		}
		return map[string]any{"billing": mode == "platform", "charged_cents": 0}, tx.Commit()
	}
	if d.AdminActor != "" {
		if _, err = tx.Exec("UPDATE billing_calls SET reconciliation_note=? WHERE id=?", d.ReconciliationNote, d.ID); err != nil {
			return nil, err
		}
		audit, _ := json.Marshal(map[string]any{"call_id": d.ID, "input_tokens": d.Input, "output_tokens": d.Output, "cached_input_tokens": d.Cached, "note": d.ReconciliationNote})
		if _, err = tx.Exec("INSERT INTO admin_audit VALUES(?,?,?,?,?)", randomID(16), d.AdminActor, "usage.reconcile", string(audit), time.Now().Unix()); err != nil {
			return nil, err
		}
	}
	if !d.Metered {
		if _, err = tx.Exec("UPDATE billing_calls SET status='unmetered',usage=? WHERE id=?", string(mustJSON(safeUsage(d.Usage))), d.ID); err != nil {
			return nil, err
		}
		if err = tx.Commit(); err != nil {
			return nil, err
		}
		return map[string]any{"billing": true, "pending_reconciliation": true}, nil
	}
	var rate Rate
	if err = json.Unmarshal([]byte(price), &rate); err != nil {
		return nil, err
	}
	if mode == "platform" && d.Model != "" && d.Model != rate.Model {
		compatible := false
		for _, candidate := range b.Prices.Rates {
			if candidate.Model == d.Model && (candidate.Input == rate.Input && candidate.Output == rate.Output && candidate.Cached == rate.Cached || candidate.Offpeak && candidate.Input/2 == rate.Input && candidate.Output/2 == rate.Output && candidate.Cached/2 == rate.Cached) {
				compatible = true
			}
		}
		if !compatible {
			return nil, errors.New("上游返回的模型与已核验价格不一致，需要核对。")
		}
	}
	cost, err := tokenCost(rate, d.Input, d.Output, d.Cached)
	if err != nil {
		return nil, err
	}
	var previousCost, previousCharge int64
	if err = tx.QueryRow("SELECT COALESCE(sum(cost_micro),0),COALESCE(sum(charged_cents),0) FROM billing_calls WHERE user_id=? AND job_id=? AND status='settled'", uid, job).Scan(&previousCost, &previousCharge); err != nil {
		return nil, err
	}
	// Round the accumulated job total once to a cent, not each model invocation.
	charge := ceil(previousCost+cost, 10000) - previousCharge
	if charge > reserve {
		if d.AdminActor == "" {
			return nil, errors.New("实际费用超过预占上限，需要人工核对。")
		}
		var otherHeld, balance int64
		if err = tx.QueryRow("SELECT COALESCE(sum(reserved_cents),0) FROM billing_calls WHERE user_id=? AND id!=? AND status IN ('reserved','unmetered')", uid, d.ID).Scan(&otherHeld); err != nil {
			return nil, err
		}
		if err = tx.QueryRow("SELECT balance_cents FROM users WHERE id=?", uid).Scan(&balance); err != nil {
			return nil, err
		}
		if balance-otherHeld < charge {
			return nil, errors.New("核对金额超过可用余额，请先处理充值后再结算。")
		}
	}
	result, err := tx.Exec("UPDATE users SET balance_cents=balance_cents-? WHERE id=? AND balance_cents>=?", charge, uid, charge)
	if err != nil {
		return nil, err
	}
	n, _ := result.RowsAffected()
	if n != 1 {
		return nil, errors.New("余额结算冲突。")
	}
	var balance int64
	if err = tx.QueryRow("SELECT balance_cents FROM users WHERE id=?", uid).Scan(&balance); err != nil {
		return nil, err
	}
	usage, _ := json.Marshal(map[string]any{"input_tokens": d.Input, "output_tokens": d.Output, "cached_input_tokens": d.Cached, "upstream": safeUsage(d.Usage)})
	if _, err = tx.Exec("UPDATE billing_calls SET cost_micro=?,charged_cents=?,reserved_cents=0,status='settled',usage=? WHERE id=?", cost, charge, string(usage), d.ID); err != nil {
		return nil, err
	}
	if charge > 0 {
		if _, err = tx.Exec("INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?)", randomID(16), uid, -charge, balance, "视频模型用量 · "+job, uid, "usage-"+d.ID, time.Now().Unix()); err != nil {
			return nil, err
		}
	}
	if err = tx.Commit(); err != nil {
		return nil, err
	}
	return map[string]any{"billing": true, "charged_cents": charge, "cost_micro": cost}, nil
}
func (s *Server) internalMeter(w http.ResponseWriter, r *http.Request) {
	raw, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 64*1024))
	if err != nil {
		fail(w, 400, "Invalid payload")
		return
	}
	stamp := r.Header.Get("X-Frame-Time")
	seconds, err := strconv.ParseInt(stamp, 10, 64)
	if err != nil || time.Now().Unix()-seconds > 90 || seconds-time.Now().Unix() > 90 {
		fail(w, 403, "Invalid signature")
		return
	}
	mac := hmac.New(sha256.New, s.Store.WorkerKey)
	mac.Write([]byte(r.URL.Path + "\n" + stamp + "\n"))
	mac.Write(raw)
	signature, err := hex.DecodeString(r.Header.Get("X-Frame-Signature"))
	if err != nil || !hmac.Equal(signature, mac.Sum(nil)) {
		fail(w, 403, "Invalid signature")
		return
	}
	var d meterRequest
	if err = json.Unmarshal(raw, &d); err != nil || !requestPattern.MatchString(d.ID) {
		fail(w, 422, "Invalid meter request")
		return
	}
	var result map[string]any
	if r.URL.Path == "/internal/billing/authorize" {
		result, err = s.Billing.authorize(d)
	} else if r.URL.Path == "/internal/billing/settle" {
		result, err = s.Billing.settle(d)
	} else {
		fail(w, 404, "Not found")
		return
	}
	if err != nil {
		if r.URL.Path == "/internal/billing/settle" {
			s.Store.DB.Exec("UPDATE billing_calls SET status='unmetered',error_type=? WHERE id=? AND user_id=? AND job_id=? AND status NOT IN ('settled','rejected')", "SettlementReviewRequired", d.ID, d.UserID, d.JobID)
		}
		fail(w, 402, err.Error())
		return
	}
	reply(w, 200, result)
}
func (s *Server) billingInfo(w http.ResponseWriter, r *http.Request) {
	var held int64
	if err := s.Store.DB.QueryRow("SELECT COALESCE(sum(reserved_cents),0) FROM billing_calls WHERE user_id=? AND status IN ('reserved','unmetered')", current(r).ID).Scan(&held); err != nil {
		s.internal(w, err)
		return
	}
	catalog, err := s.Store.catalog()
	if err != nil {
		s.internal(w, err)
		return
	}
	prepaid, err := s.Store.prepaid(current(r).ID)
	if err != nil {
		s.internal(w, err)
		return
	}
	u, err := s.Store.user(current(r).ID)
	if err != nil {
		s.internal(w, err)
		return
	}
	c, err := s.Store.config(u.ID)
	if err != nil {
		s.internal(w, err)
		return
	}
	c.UsePlatform = true
	if id := r.URL.Query().Get("text_model"); id != "" {
		c.PlatformText = id
	}
	if id := r.URL.Query().Get("vision_model"); id != "" {
		c.PlatformVision = id
	}
	effective, e := s.effective(c)
	low, high := int64(0), int64(0)
	duration, _ := strconv.Atoi(r.URL.Query().Get("duration"))
	if duration <= 0 {
		duration = 60
	}
	duration = min(duration, 600)
	if e == nil && len(effective.PlatformPrices) == 2 {
		scenes := int64(max(2, duration/15))
		t, _ := tokenCost(effective.PlatformPrices[0], 20000+scenes*6000, 5000+scenes*4500, 0)
		v, _ := tokenCost(effective.PlatformPrices[1], scenes*12000, scenes*1000, 0)
		low = ceil(t+v, 10000)
		high = low * 3
	}
	reply(w, 200, map[string]any{"platform_available": s.platformAvailable(catalog), "enabled": s.Billing.Enabled, "charge_byok": false, "held_cents": held, "balance_cents": u.Balance, "available_cents": max(0, u.Balance-held), "prepaid": prepaid, "minimum_deposit_cents": 500, "currency": "CNY", "catalog": catalog.public(false), "estimate_low_cents": low, "estimate_high_cents": high, "service_fee_cents": 0})
}

func (s *Store) platform() (PersonalConfig, error) {
	c := defaultConfig()
	raw, err := os.ReadFile(filepath.Join(s.Dir, "platform.enc"))
	if err != nil {
		return c, err
	}
	n := s.Cipher.NonceSize()
	if len(raw) < n {
		return c, errors.New("invalid platform config")
	}
	plain, err := s.Cipher.Open(nil, raw[:n], raw[n:], []byte("platform"))
	if err != nil {
		return c, err
	}
	err = json.Unmarshal(plain, &c)
	return c, err
}
func (s *Store) importPlatform(filename string) error {
	raw, err := os.ReadFile(filename)
	if err != nil {
		return err
	}
	c := defaultConfig()
	c.VisionInherit = false
	if err = json.Unmarshal(raw, &c); err != nil {
		return err
	}
	// Only the two authorized generation/review models are platform-paid. Speech remains free.
	c.UsePlatform = true
	c.Text.Fallbacks = []string{}
	c.Vision.Fallbacks = []string{}
	c.TTS = defaultConfig().TTS
	for _, channel := range []*Channel{&c.Text, &c.Vision} {
		channel.APIKey, err = importedAPIKey(channel.APIKey)
		if err != nil {
			return err
		}
	}
	if !c.public().TextReady || !c.public().VisionReady {
		return errors.New("platform model keys, endpoints and model names are required")
	}
	if err = normalizeConfig(&c, defaultConfig()); err != nil {
		return err
	}
	raw, err = json.Marshal(c)
	if err != nil {
		return err
	}
	nonce := make([]byte, s.Cipher.NonceSize())
	if _, err = rand.Read(nonce); err != nil {
		return err
	}
	encrypted := s.Cipher.Seal(nonce, nonce, raw, []byte("platform"))
	return os.WriteFile(filepath.Join(s.Dir, "platform.enc"), encrypted, 0600)
}

var keyEnvironmentReference = regexp.MustCompile(`^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$`)

func importedAPIKey(value string) (string, error) {
	value = strings.TrimSpace(value)
	if match := keyEnvironmentReference.FindStringSubmatch(value); match != nil {
		resolved, ok := os.LookupEnv(match[1])
		if !ok || strings.TrimSpace(resolved) == "" {
			return "", errors.New("platform API key environment variable is unset: " + match[1])
		}
		value = strings.TrimSpace(resolved)
	}
	if strings.Contains(value, "${") {
		return "", errors.New("unresolved platform API key environment reference")
	}
	return value, nil
}
func (s *Server) effective(c PersonalConfig) (PersonalConfig, error) {
	if !c.UsePlatform {
		return c, nil
	}
	if !s.Billing.Enabled {
		return c, errors.New("平台模型服务尚未开通计费，请先使用个人 API 配置。")
	}
	catalog, err := s.Store.catalog()
	if err == nil && len(catalog.Models) > 0 {
		text, e := catalog.model(c.PlatformText, "text")
		if e != nil {
			return c, e
		}
		vision, e := catalog.model(c.PlatformVision, "vision")
		if e != nil {
			return c, e
		}
		if c.TTS.Provider != "edge" {
			return c, errors.New("平台模式仅支持免费在线配音。")
		}
		c.Text = text.Channel
		c.Vision = vision.Channel
		c.VisionInherit = false
		c.PlatformText = text.ID
		c.PlatformVision = vision.ID
		text.Price.Role = "text"
		vision.Price.Role = "vision"
		text.Price.Revision = catalog.Revision
		vision.Price.Revision = catalog.Revision
		c.PlatformPrices = []Rate{text.Price, vision.Price}
		return c, nil
	}
	platform, err := s.Store.platform()
	if err != nil {
		return c, errors.New("平台模型服务尚未配置。")
	}
	// Preserve the user's choice among free voices, never permit paid speech on platform funds.
	if c.TTS.Provider != "edge" {
		return c, errors.New("平台模式仅支持免费在线配音。")
	}
	platform.TTS = c.TTS
	return platform, nil
}

func mustJSON(v any) []byte { raw, _ := json.Marshal(v); return raw }

func (s *Server) platformAvailable(c PlatformCatalog) bool {
	if !s.Billing.Enabled {
		return false
	}
	_, a := c.model(c.DefaultText, "text")
	_, b := c.model(c.DefaultVision, "vision")
	return a == nil && b == nil
}
