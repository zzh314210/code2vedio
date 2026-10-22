package main

import (
	"strings"
	"testing"
)

func TestRaiseOutputLimitPreservesTaskIdentityAndBilling(t *testing.T) {
	store, s := fixture(t)
	u, _ := registered(t, s, "output-budget")
	c := defaultConfig()
	c.Text.APIKey = "private-task-key"
	c.Text.Model = "deepseek-test"
	c.UsePlatform = true
	c.Vision.MaxTokens = 12000
	if err := store.saveTaskConfig(u.ID, "failed-task", c); err != nil {
		t.Fatal(err)
	}
	if n, err := store.raiseTextOutputLimit(65536, "failed-task"); err != nil || n != 1 {
		t.Fatal(n, err)
	}
	got, err := store.taskConfig(u.ID, "failed-task")
	c.Text.MaxTokens = 65536
	if err != nil || string(mustJSON(got)) != string(mustJSON(c)) {
		t.Fatal("changed archived identity, credentials, billing, vision or thinking policy", err)
	}
	if n, err := store.raiseTextOutputLimit(24000, "failed-task"); err != nil || n != 0 {
		t.Fatal("must not lower an explicit output budget", n, err)
	}
	var detail string
	if err := store.DB.QueryRow("SELECT detail FROM admin_audit WHERE action='task.output_limit'").Scan(&detail); err != nil || strings.Contains(detail, "private-task-key") || !strings.Contains(detail, "65536") {
		t.Fatal("audit absent or leaked credentials", err)
	}
	if _, err := store.taskConfig("another-user", "failed-task"); err == nil {
		t.Fatal("task ownership bypassed")
	}
}

func TestRaisePlatformOutputLimitTouchesOnlyEnabledText(t *testing.T) {
	store, _ := fixture(t)
	c := PlatformCatalog{Models: []PlatformModel{
		{ID: "text", Role: "text", Enabled: true, Channel: Channel{APIKey: "secret", Model: "kimi", MaxTokens: 24000}, Price: Rate{Input: 100, Output: 200}},
		{ID: "vision", Role: "vision", Enabled: true, Channel: Channel{MaxTokens: 24000}},
		{ID: "disabled", Role: "text", Channel: Channel{MaxTokens: 12000}},
		{ID: "larger", Role: "text", Enabled: true, Channel: Channel{MaxTokens: 90000}},
	}}
	if err := store.saveCatalog(c, store.adminID()); err != nil {
		t.Fatal(err)
	}
	if n, err := store.raiseTextOutputLimit(65536, ""); err != nil || n != 1 {
		t.Fatal(n, err)
	}
	c.Models[0].Channel.MaxTokens = 65536
	c.Revision++
	got, _ := store.catalog()
	if string(mustJSON(got)) != string(mustJSON(c)) {
		t.Fatal("unexpected catalog change")
	}
	if n, err := store.raiseTextOutputLimit(65536, ""); err != nil || n != 0 {
		t.Fatal("not idempotent", n, err)
	}
	if _, err := store.raiseTextOutputLimit(100001, ""); err == nil {
		t.Fatal("invalid limit accepted")
	}
}
