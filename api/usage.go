package main

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"
)

func truncate(s string, n int) string {
	r := []rune(s)
	if len(r) > n {
		return string(r[:n])
	}
	return s
}
func safeReasoning(src map[string]any) map[string]any {
	out := map[string]any{}
	for _, key := range []string{"provider", "requested_effort", "effective_effort"} {
		if value, ok := src[key].(string); ok {
			out[key] = truncate(value, 100)
		}
	}
	if enabled, ok := src["enabled"].(bool); ok {
		out["enabled"] = enabled
	}
	return out
}
func safeUsage(raw json.RawMessage) map[string]any {
	var src map[string]any
	json.Unmarshal(raw, &src)
	out := map[string]any{}
	for _, k := range []string{"prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"} {
		if n, ok := src[k].(float64); ok && n >= 0 {
			out[k] = n
		}
	}
	for _, k := range []string{"prompt_tokens_details", "completion_tokens_details", "input_tokens_details", "output_tokens_details"} {
		if v, ok := src[k].(map[string]any); ok {
			detail := map[string]any{}
			for _, key := range []string{"cached_tokens", "reasoning_tokens", "audio_tokens", "image_tokens"} {
				if n, ok := v[key].(float64); ok && n >= 0 {
					detail[key] = n
				}
			}
			out[k] = detail
		}
	}
	return out
}
func (b *Billing) migrateUsage() error {
	columns := map[string]string{"reconciliation_note": "TEXT NOT NULL DEFAULT ''", "mode": "TEXT NOT NULL DEFAULT 'platform'", "duration_ms": "INTEGER NOT NULL DEFAULT 0", "first_token_ms": "INTEGER NOT NULL DEFAULT 0", "finished_at": "INTEGER NOT NULL DEFAULT 0", "response_id": "TEXT NOT NULL DEFAULT ''", "actual_model": "TEXT NOT NULL DEFAULT ''", "error_type": "TEXT NOT NULL DEFAULT ''", "stage": "TEXT NOT NULL DEFAULT ''", "stream": "INTEGER NOT NULL DEFAULT 0"}
	rows, err := b.Store.DB.Query("PRAGMA table_info(billing_calls)")
	if err != nil {
		return err
	}
	existing := map[string]bool{}
	for rows.Next() {
		var id, notnull, pk int
		var name, kind string
		var def any
		if err = rows.Scan(&id, &name, &kind, &notnull, &def, &pk); err != nil {
			rows.Close()
			return err
		}
		existing[name] = true
	}
	rows.Close()
	for name, kind := range columns {
		if !existing[name] {
			if _, err = b.Store.DB.Exec("ALTER TABLE billing_calls ADD COLUMN " + name + " " + kind); err != nil {
				return err
			}
		}
	}
	_, err = b.Store.DB.Exec("CREATE INDEX IF NOT EXISTS billing_calls_user_time ON billing_calls(user_id,created_at DESC)")
	return err
}

type UsageRecord struct {
	ReconciliationNote string          `json:"reconciliation_note"`
	ID                 string          `json:"id"`
	UserID             string          `json:"user_id"`
	Username           string          `json:"username"`
	JobID              string          `json:"job_id"`
	Model              string          `json:"model"`
	Role               string          `json:"role"`
	Mode               string          `json:"mode"`
	Status             string          `json:"status"`
	Price              Rate            `json:"price"`
	Usage              json.RawMessage `json:"usage"`
	Reserved           int64           `json:"reserved_cents"`
	Cost               int64           `json:"cost_micro"`
	Charged            int64           `json:"charged_cents"`
	CreatedAt          int64           `json:"created_at"`
	FinishedAt         int64           `json:"finished_at"`
	Duration           int64           `json:"duration_ms"`
	FirstToken         int64           `json:"first_token_ms"`
	ResponseID         string          `json:"response_id"`
	ActualModel        string          `json:"actual_model"`
	ErrorType          string          `json:"error_type"`
	Stage              string          `json:"stage"`
	Stream             bool            `json:"stream"`
}

func (s *Server) usageList(w http.ResponseWriter, r *http.Request) {
	admin := strings.HasPrefix(r.URL.Path, "/api/admin/")
	if admin && !requireAdmin(w, r) {
		return
	}
	q := r.URL.Query()
	where := []string{"b.mode='platform'"}
	args := []any{}
	uid := current(r).ID
	if admin {
		uid = q.Get("user_id")
	}
	if uid != "" {
		where = append(where, "b.user_id=?")
		args = append(args, uid)
	}
	for _, key := range []string{"model", "role", "status", "mode", "job_id"} {
		if v := q.Get(key); v != "" {
			where = append(where, "b."+key+"=?")
			args = append(args, v)
		}
	}
	for _, key := range []string{"from", "to"} {
		if v := q.Get(key); v != "" {
			d, err := time.Parse("2006-01-02", v)
			if err != nil {
				fail(w, 422, "日期格式应为 YYYY-MM-DD。")
				return
			}
			op := ">="
			if key == "to" {
				d = d.Add(24 * time.Hour)
				op = "<"
			}
			where = append(where, "b.created_at"+op+"?")
			args = append(args, d.Unix())
		}
	}
	clause := strings.Join(where, " AND ")
	offset, _ := strconv.Atoi(q.Get("offset"))
	offset = max(0, offset)
	limit := 50
	var total int
	var cost, charged, input, output, cached int64
	err := s.Store.DB.QueryRow(`SELECT count(*),COALESCE(sum(cost_micro),0),COALESCE(sum(charged_cents),0),COALESCE(sum(json_extract(usage,'$.input_tokens')),0),COALESCE(sum(json_extract(usage,'$.output_tokens')),0),COALESCE(sum(json_extract(usage,'$.cached_input_tokens')),0) FROM billing_calls b WHERE `+clause, args...).Scan(&total, &cost, &charged, &input, &output, &cached)
	if err != nil {
		s.internal(w, err)
		return
	}
	rows, err := s.Store.DB.Query(`SELECT b.id,b.user_id,u.username,b.job_id,b.model,b.role,b.mode,b.status,b.price,b.usage,b.reserved_cents,b.cost_micro,b.charged_cents,b.created_at,b.finished_at,b.duration_ms,b.first_token_ms,b.response_id,b.actual_model,b.error_type,b.stage,b.stream,b.reconciliation_note FROM billing_calls b JOIN users u ON u.id=b.user_id WHERE `+clause+` ORDER BY b.created_at DESC,b.rowid DESC LIMIT ? OFFSET ?`, append(args, limit, offset)...)
	if err != nil {
		s.internal(w, err)
		return
	}
	defer rows.Close()
	items := []UsageRecord{}
	for rows.Next() {
		var d UsageRecord
		var price, usage string
		if err = rows.Scan(&d.ID, &d.UserID, &d.Username, &d.JobID, &d.Model, &d.Role, &d.Mode, &d.Status, &price, &usage, &d.Reserved, &d.Cost, &d.Charged, &d.CreatedAt, &d.FinishedAt, &d.Duration, &d.FirstToken, &d.ResponseID, &d.ActualModel, &d.ErrorType, &d.Stage, &d.Stream, &d.ReconciliationNote); err != nil {
			s.internal(w, err)
			return
		}
		if err = json.Unmarshal([]byte(price), &d.Price); err != nil {
			s.internal(w, err)
			return
		}
		d.Usage = json.RawMessage(usage)
		items = append(items, d)
	}
	if err = rows.Err(); err != nil {
		s.internal(w, err)
		return
	}
	reply(w, 200, map[string]any{"items": items, "total": total, "offset": offset, "limit": limit, "summary": map[string]any{"cost_micro": cost, "charged_cents": charged, "input_tokens": input, "output_tokens": output, "cached_input_tokens": cached}})
}
func (s *Server) ledgerList(w http.ResponseWriter, r *http.Request) {
	uid := current(r).ID
	if strings.HasPrefix(r.URL.Path, "/api/admin/") {
		if !requireAdmin(w, r) {
			return
		}
		uid = r.PathValue("id")
	}
	q := r.URL.Query()
	offset, _ := strconv.Atoi(q.Get("offset"))
	offset = max(0, offset)
	where := "user_id=?"
	args := []any{uid}
	if q.Get("kind") == "deposit" {
		where += " AND request_id NOT LIKE 'usage-%'"
	}
	var total int
	if err := s.Store.DB.QueryRow("SELECT count(*) FROM ledger WHERE "+where, args...).Scan(&total); err != nil {
		s.internal(w, err)
		return
	}
	rows, err := s.Store.DB.Query("SELECT l.*,COALESCE(u.display_name,'') FROM ledger l LEFT JOIN users u ON u.id=l.actor_id WHERE "+where+" ORDER BY l.created_at DESC,l.rowid DESC LIMIT 50 OFFSET ?", append(args, offset)...)
	if err != nil {
		s.internal(w, err)
		return
	}
	defer rows.Close()
	items := []Entry{}
	for rows.Next() {
		var d Entry
		e := rows.Scan(&d.ID, &d.UserID, &d.Amount, &d.Balance, &d.Note, &d.ActorID, &d.RequestID, &d.CreatedAt, &d.ActorName)
		if e != nil {
			s.internal(w, e)
			return
		}
		items = append(items, d)
	}
	if err = rows.Err(); err != nil {
		s.internal(w, err)
		return
	}
	reply(w, 200, map[string]any{"items": items, "total": total, "offset": offset, "limit": 50})
}

func (s *Server) reconcileUsage(w http.ResponseWriter, r *http.Request) {
	if !requireAdmin(w, r) {
		return
	}
	var d struct {
		Input  int64  `json:"input_tokens"`
		Output int64  `json:"output_tokens"`
		Cached int64  `json:"cached_input_tokens"`
		Note   string `json:"note"`
	}
	if !decode(w, r, &d) {
		return
	}
	d.Note = strings.TrimSpace(d.Note)
	if len([]rune(d.Note)) < 5 || len([]rune(d.Note)) > 300 {
		fail(w, 422, "请填写核对依据（5至300字）。")
		return
	}
	var m meterRequest
	var created int64
	var status string
	err := s.Store.DB.QueryRow("SELECT user_id,job_id,model,created_at,status FROM billing_calls WHERE id=? AND mode='platform'", r.PathValue("id")).Scan(&m.UserID, &m.JobID, &m.Model, &created, &status)
	if err != nil {
		fail(w, 404, "调用记录不存在。")
		return
	}
	if status == "reserved" && time.Now().Unix()-created < 900 {
		fail(w, 409, "调用可能仍在执行，请结束后再核对（至少等待15分钟）。")
		return
	}
	m.ID = r.PathValue("id")
	m.Metered = true
	m.Input = d.Input
	m.Output = d.Output
	m.Cached = d.Cached
	m.Usage = json.RawMessage(`{}`)
	m.AdminActor = current(r).ID
	m.ReconciliationNote = d.Note
	result, err := s.Billing.settle(m)
	if err != nil {
		fail(w, 409, err.Error())
		return
	}
	reply(w, 200, result)
}
