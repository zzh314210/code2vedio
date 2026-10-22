package main

import (
	"crypto/rand"
	"encoding/json"
	"errors"
	"time"
)

// Maintenance is explicit: never silently change a user's chosen model, price,
// key or thinking policy. Archived tasks need their own audited budget update.
func (s *Store) raiseTextOutputLimit(limit int, job string) (int, error) {
	if limit < 256 || limit > 100000 {
		return 0, errors.New("output limit must be between 256 and 100000")
	}
	if job == "" {
		c, err := s.catalog()
		if err != nil {
			return 0, err
		}
		n := 0
		for i := range c.Models {
			m := &c.Models[i]
			if m.Enabled && m.Role == "text" && m.Channel.MaxTokens < limit {
				m.Channel.MaxTokens = limit
				n++
			}
		}
		if n == 0 {
			return 0, nil
		}
		c.Revision++
		return n, s.saveCatalog(c, s.adminID())
	}
	var uid string
	var previous []byte
	if err := s.DB.QueryRow("SELECT user_id,ciphertext FROM task_configs WHERE job_id=?", job).Scan(&uid, &previous); err != nil {
		return 0, err
	}
	c, err := s.taskConfig(uid, job)
	if err != nil {
		return 0, err
	}
	if c.Text.MaxTokens >= limit {
		return 0, nil
	}
	before := c.Text.MaxTokens
	c.Text.MaxTokens = limit
	raw, err := json.Marshal(c)
	if err != nil {
		return 0, err
	}
	nonce := make([]byte, s.Cipher.NonceSize())
	if _, err = rand.Read(nonce); err != nil {
		return 0, err
	}
	encrypted := s.Cipher.Seal(nonce, nonce, raw, []byte(uid+":"+job))
	detail, _ := json.Marshal(map[string]any{"job_id": job, "user_id": uid, "previous": before, "max_tokens": limit})
	actor := s.adminID()
	tx, err := s.DB.Begin()
	if err != nil {
		return 0, err
	}
	defer tx.Rollback()
	result, err := tx.Exec("UPDATE task_configs SET ciphertext=? WHERE job_id=? AND user_id=? AND ciphertext=?", encrypted, job, uid, previous)
	if err != nil {
		return 0, err
	}
	if n, err := result.RowsAffected(); err != nil || n != 1 {
		return 0, errors.New("task configuration changed concurrently; retry maintenance")
	}
	if _, err = tx.Exec("INSERT INTO admin_audit VALUES(?,?,?,?,?)", randomID(16), actor, "task.output_limit", string(detail), time.Now().Unix()); err != nil {
		return 0, err
	}
	return 1, tx.Commit()
}
