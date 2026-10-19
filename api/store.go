package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"golang.org/x/crypto/bcrypt"
	_ "modernc.org/sqlite"
)

type User struct {
	ID          string `json:"id"`
	Username    string `json:"username"`
	DisplayName string `json:"display_name"`
	Role        string `json:"role"`
	Active      bool   `json:"active"`
	Balance     int64  `json:"balance_cents"`
	CreatedAt   int64  `json:"created_at"`
	Password    string `json:"-"`
	SessionID   string `json:"-"`
}
type Store struct {
	DB        *sql.DB
	Cipher    cipher.AEAD
	WorkerKey []byte
	Dir       string
}

func randomID(n int) string {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return hex.EncodeToString(b)
}
func hashToken(s string) string { v := sha256.Sum256([]byte(s)); return hex.EncodeToString(v[:]) }
func readOrCreateKey(path string, mustExist bool) ([]byte, error) {
	data, err := os.ReadFile(path)
	if err == nil {
		if len(data) != 32 {
			return nil, errors.New("invalid key length")
		}
		return data, nil
	}
	if !os.IsNotExist(err) || mustExist {
		return nil, fmt.Errorf("key unavailable; restore backup: %w", err)
	}
	data = make([]byte, 32)
	if _, err = rand.Read(data); err != nil {
		return nil, err
	}
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	_, err = f.Write(data)
	return data, err
}
func openStore(dir string) (*Store, error) {
	if err := os.MkdirAll(dir, 0700); err != nil {
		return nil, err
	}
	if err := os.Chmod(dir, 0700); err != nil {
		return nil, err
	}
	_, e := os.Stat(filepath.Join(dir, "users.sqlite3"))
	key, err := readOrCreateKey(filepath.Join(dir, "users.key"), e == nil)
	if err != nil {
		return nil, err
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	workerKey, err := readOrCreateKey(filepath.Join(dir, "worker.key"), false)
	if err != nil {
		return nil, err
	}
	db, err := sql.Open("sqlite", filepath.Join(dir, "users.sqlite3"))
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	schema := `PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=10000;
 CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,display_name TEXT NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'user',active INTEGER NOT NULL DEFAULT 1,balance_cents INTEGER NOT NULL DEFAULT 0 CHECK(balance_cents>=0),created_at INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),token_hash TEXT UNIQUE NOT NULL,created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,agent TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS configs(user_id TEXT PRIMARY KEY REFERENCES users(id),ciphertext BLOB NOT NULL);
 CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),amount_cents INTEGER NOT NULL,balance_cents INTEGER NOT NULL,note TEXT NOT NULL,actor_id TEXT NOT NULL REFERENCES users(id),request_id TEXT UNIQUE NOT NULL,created_at INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS rate_limits(key TEXT PRIMARY KEY,count INTEGER NOT NULL,reset_at INTEGER NOT NULL);`
	if _, err = db.Exec(schema); err != nil {
		db.Close()
		return nil, err
	}
	os.Chmod(filepath.Join(dir, "users.sqlite3"), 0600)
	store := &Store{DB: db, Cipher: aead, WorkerKey: workerKey, Dir: dir}
	if err := store.initAutomation(); err != nil {
		db.Close()
		return nil, err
	}
	return store, nil
}

const userFields = "id,username,display_name,role,active,balance_cents,created_at,password"

type scanner interface{ Scan(...any) error }

func scanUser(row scanner) (User, error) {
	var u User
	err := row.Scan(&u.ID, &u.Username, &u.DisplayName, &u.Role, &u.Active, &u.Balance, &u.CreatedAt, &u.Password)
	return u, err
}
func (s *Store) user(id string) (User, error) {
	return scanUser(s.DB.QueryRow("SELECT "+userFields+" FROM users WHERE id=?", id))
}
func (s *Store) createUser(name, password, display, role string) (User, error) {
	hashed, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return User{}, err
	}
	if display == "" {
		display = name
	}
	u := User{ID: randomID(16), Username: name, DisplayName: display, Role: role, Active: true, CreatedAt: time.Now().Unix()}
	_, err = s.DB.Exec("INSERT INTO users(id,username,display_name,password,role,created_at) VALUES(?,?,?,?,?,?)", u.ID, name, display, string(hashed), role, u.CreatedAt)
	return u, err
}
func (s *Store) bootstrap() error {
	var count int
	if err := s.DB.QueryRow("SELECT count(*) FROM users WHERE role='admin'").Scan(&count); err != nil {
		return err
	}
	if count > 0 {
		return nil
	}
	password := randomID(18)
	// Persist the recovery credential before creating the account; never log its value.
	path := filepath.Join(s.Dir, "admin-access.txt")
	if err := os.WriteFile(path, []byte("USERNAME=admin\nPASSWORD="+password+"\n"), 0600); err != nil {
		return err
	}
	_, err := s.createUser("admin", password, "管理员", "admin")
	return err
}
func (s *Store) adminID() string {
	var id string
	s.DB.QueryRow("SELECT id FROM users WHERE role='admin' ORDER BY created_at LIMIT 1").Scan(&id)
	return id
}
func (s *Store) authenticate(token string) (User, error) {
	if token == "" || len(token) > 256 {
		return User{}, sql.ErrNoRows
	}
	var id, sid string
	err := s.DB.QueryRow("SELECT user_id,id FROM sessions WHERE token_hash=? AND expires_at>?", hashToken(token), time.Now().Unix()).Scan(&id, &sid)
	if err != nil {
		return User{}, err
	}
	u, err := s.user(id)
	if err != nil || !u.Active {
		return User{}, sql.ErrNoRows
	}
	u.SessionID = sid
	return u, nil
}
func (s *Store) config(uid string) (PersonalConfig, error) {
	c := defaultConfig()
	var encrypted []byte
	err := s.DB.QueryRow("SELECT ciphertext FROM configs WHERE user_id=?", uid).Scan(&encrypted)
	if errors.Is(err, sql.ErrNoRows) {
		return c, nil
	}
	if err != nil {
		return c, err
	}
	n := s.Cipher.NonceSize()
	if len(encrypted) < n {
		return c, errors.New("invalid encrypted config")
	}
	raw, err := s.Cipher.Open(nil, encrypted[:n], encrypted[n:], []byte(uid))
	if err != nil {
		return c, err
	}
	err = json.Unmarshal(raw, &c)
	return c, err
}
func (s *Store) saveConfig(uid string, c PersonalConfig) error {
	raw, err := json.Marshal(c)
	if err != nil {
		return err
	}
	nonce := make([]byte, s.Cipher.NonceSize())
	if _, err = rand.Read(nonce); err != nil {
		return err
	}
	encrypted := s.Cipher.Seal(nonce, nonce, raw, []byte(uid))
	_, err = s.DB.Exec("INSERT INTO configs VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET ciphertext=excluded.ciphertext", uid, encrypted)
	return err
}
func (s *Store) limit(key string, max int, seconds int64) error {
	tx, err := s.DB.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	now := time.Now().Unix()
	if _, err = tx.Exec("DELETE FROM rate_limits WHERE reset_at<?", now); err != nil {
		return err
	}
	var count int
	err = tx.QueryRow("SELECT count FROM rate_limits WHERE key=?", key).Scan(&count)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return err
	}
	if count >= max {
		return errors.New("操作过于频繁，请稍后再试。")
	}
	if _, err = tx.Exec("INSERT INTO rate_limits VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1", key, now+seconds); err != nil {
		return err
	}
	return tx.Commit()
}

type Entry struct {
	ID        string `json:"id"`
	UserID    string `json:"user_id"`
	Amount    int64  `json:"amount_cents"`
	Balance   int64  `json:"balance_cents"`
	Note      string `json:"note"`
	ActorID   string `json:"actor_id"`
	RequestID string `json:"request_id"`
	CreatedAt int64  `json:"created_at"`
}

func scanEntry(row scanner) (Entry, error) {
	var e Entry
	err := row.Scan(&e.ID, &e.UserID, &e.Amount, &e.Balance, &e.Note, &e.ActorID, &e.RequestID, &e.CreatedAt)
	return e, err
}
func (s *Store) credit(actor, uid string, amount int64, note, requestID string) (Entry, error) {
	tx, err := s.DB.Begin()
	if err != nil {
		return Entry{}, err
	}
	defer tx.Rollback()
	old, err := scanEntry(tx.QueryRow("SELECT * FROM ledger WHERE request_id=?", requestID))
	if err == nil {
		if old.UserID != uid || old.ActorID != actor || old.Amount != amount || old.Note != note {
			return Entry{}, errors.New("充值凭证已用于另一笔操作。")
		}
		return old, nil
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return Entry{}, err
	}
	var balance int64
	if err = tx.QueryRow("SELECT balance_cents FROM users WHERE id=?", uid).Scan(&balance); err != nil {
		return Entry{}, errors.New("用户不存在。")
	}
	if amount <= 0 || amount > 100000000 || balance > 10000000000-amount {
		return Entry{}, errors.New("充值金额超出范围。")
	}
	e := Entry{randomID(16), uid, amount, balance + amount, note, actor, requestID, time.Now().Unix()}
	if _, err = tx.Exec("UPDATE users SET balance_cents=? WHERE id=?", e.Balance, uid); err != nil {
		return e, err
	}
	if _, err = tx.Exec("INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?)", e.ID, e.UserID, e.Amount, e.Balance, e.Note, e.ActorID, e.RequestID, e.CreatedAt); err != nil {
		return e, err
	}
	return e, tx.Commit()
}
func (s *Store) ledger(uid string) ([]Entry, error) {
	rows, err := s.DB.Query("SELECT * FROM ledger WHERE user_id=? ORDER BY created_at DESC,rowid DESC LIMIT 200", uid)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	entries := []Entry{}
	for rows.Next() {
		e, err := scanEntry(rows)
		if err != nil {
			return nil, err
		}
		entries = append(entries, e)
	}
	return entries, rows.Err()
}
func duplicate(err error) bool {
	return err != nil && strings.Contains(err.Error(), "UNIQUE constraint")
}

func (s *Store) resetPassword(username, password string) error {
	if len([]rune(password)) < 10 || len(password) > 72 {
		return errors.New("new password must have at least 10 characters, at most 72 bytes")
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return err
	}
	tx, err := s.DB.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	var id string
	if err = tx.QueryRow("SELECT id FROM users WHERE username=?", strings.ToLower(username)).Scan(&id); err != nil {
		return err
	}
	if _, err = tx.Exec("UPDATE users SET password=? WHERE id=?", string(hash), id); err != nil {
		return err
	}
	if _, err = tx.Exec("DELETE FROM sessions WHERE user_id=?", id); err != nil {
		return err
	}
	return tx.Commit()
}
