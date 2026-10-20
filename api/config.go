package main

import (
	"context"
	"errors"
	"net"
	"net/url"
	"strings"
	"time"
)

type Channel struct {
	MaxTokens     int             `json:"max_tokens,omitempty"`
	Stream        bool            `json:"stream,omitempty"`
	ExtraBody     map[string]bool `json:"extra_body,omitempty"`
	BaseURL       string          `json:"base_url"`
	Model         string          `json:"model"`
	APIKey        string          `json:"api_key,omitempty"`
	Protocol      string          `json:"protocol,omitempty"`
	Fallbacks     []string        `json:"fallback_models"`
	ClearKey      bool            `json:"clear_key,omitempty"`
	KeyConfigured bool            `json:"key_configured"`
	Provider      string          `json:"provider,omitempty"`
	Voice         string          `json:"voice,omitempty"`
}
type PersonalConfig struct {
	Saved          bool    `json:"saved"`
	PlatformText   string  `json:"platform_text_model,omitempty"`
	PlatformVision string  `json:"platform_vision_model,omitempty"`
	PlatformPrices []Rate  `json:"platform_prices,omitempty"`
	UsePlatform    bool    `json:"use_platform"`
	Text           Channel `json:"text"`
	Vision         Channel `json:"vision"`
	TTS            Channel `json:"tts"`
	VisionInherit  bool    `json:"vision_inherit"`
	TextReady      bool    `json:"text_ready"`
	VisionReady    bool    `json:"vision_ready"`
	SpeechReady    bool    `json:"speech_ready"`
}

func defaultConfig() PersonalConfig {
	return PersonalConfig{Text: Channel{MaxTokens: 24000, Protocol: "chat_completions", Fallbacks: []string{}}, Vision: Channel{MaxTokens: 6000, Protocol: "chat_completions", Fallbacks: []string{}}, VisionInherit: false, TTS: Channel{Provider: "edge", Voice: "zh-CN-XiaoxiaoNeural", Fallbacks: []string{}}}
}
func (c PersonalConfig) public() PersonalConfig {
	c.PlatformPrices = nil
	ready := func(ch Channel) bool { return ch.BaseURL != "" && ch.Model != "" && ch.APIKey != "" }
	c.TextReady = ready(c.Text)
	c.VisionReady = ready(c.Vision)
	if c.VisionInherit {
		c.VisionReady = c.TextReady
	}
	c.SpeechReady = c.TTS.Provider == "edge" || (ready(c.TTS) && c.TTS.Voice != "")
	for _, ch := range []*Channel{&c.Text, &c.Vision, &c.TTS} {
		ch.KeyConfigured = ch.APIKey != ""
		ch.APIKey = ""
		ch.ClearKey = false
	}
	return c
}
func publicIP(ip net.IP) bool {
	return ip.IsGlobalUnicast() && !ip.IsPrivate() && !ip.IsLoopback() && !ip.IsLinkLocalUnicast() && !ip.IsLinkLocalMulticast() && !ip.IsUnspecified() && !reservedIP(ip)
}
func reservedIP(ip net.IP) bool {
	for _, cidr := range []string{"0.0.0.0/8", "100.64.0.0/10", "192.0.0.0/24", "192.0.2.0/24", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "240.0.0.0/4", "2001:db8::/32", "2001::/32", "2002::/16"} {
		_, n, _ := net.ParseCIDR(cidr)
		if n.Contains(ip) {
			return true
		}
	}
	return false
}
func validateEndpoint(raw string) error {
	u, err := url.Parse(raw)
	if err != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || (u.Port() != "" && u.Port() != "443") {
		return errors.New("请填写服务商提供的公开 HTTPS 接口地址（443端口）。")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	ips, err := net.DefaultResolver.LookupIPAddr(ctx, u.Hostname())
	if err != nil || len(ips) == 0 {
		return errors.New("接口域名无法解析，请检查地址。")
	}
	for _, ip := range ips {
		if !publicIP(ip.IP) {
			return errors.New("模型接口不能指向内网或保留地址。")
		}
	}
	return nil
}
func normalizeConfig(c *PersonalConfig, old PersonalConfig) error {
	for i, ch := range []*Channel{&c.Text, &c.Vision, &c.TTS} {
		if ch.MaxTokens < 0 || ch.MaxTokens > 100000 {
			return errors.New("最大输出需在1至100000 token范围内。")
		}
		for key := range ch.ExtraBody {
			if key != "enable_thinking" {
				return errors.New("不支持的扩展模型参数。")
			}
		}
		previous := []Channel{old.Text, old.Vision, old.TTS}[i]
		ch.BaseURL = strings.TrimRight(strings.TrimSpace(ch.BaseURL), "/")
		ch.Model = strings.TrimSpace(ch.Model)
		ch.APIKey = strings.TrimSpace(ch.APIKey)
		if strings.Contains(ch.APIKey, "${") {
			return errors.New("请填写实际 API Key，不能使用环境变量占位符。")
		}
		if len(ch.BaseURL) > 500 || len(ch.Model) > 150 || len(ch.APIKey) > 2048 || strings.ContainsAny(ch.Model, "\r\n") || strings.ContainsAny(ch.APIKey, "\r\n") {
			return errors.New("接口、模型或密钥格式不正确。")
		}
		if ch.BaseURL != "" {
			if err := validateEndpoint(ch.BaseURL); err != nil {
				return err
			}
		}
		if ch.ClearKey {
			ch.APIKey = ""
		} else if ch.APIKey == "" && ch.BaseURL == previous.BaseURL {
			ch.APIKey = previous.APIKey
		}
		ch.ClearKey = false
		ch.KeyConfigured = false
		if i < 2 {
			if ch.Protocol != "responses" && ch.Protocol != "chat_completions" {
				return errors.New("请选择支持的接口协议。")
			}
			if len(ch.Fallbacks) > 8 {
				return errors.New("最多配置8个备用模型。")
			}
			for j, m := range ch.Fallbacks {
				m = strings.TrimSpace(m)
				if m == "" || len(m) > 150 || strings.ContainsAny(m, "\r\n") {
					return errors.New("备用模型名称无效。")
				}
				ch.Fallbacks[j] = m
			}
		}
	}
	if c.TTS.Provider != "edge" && c.TTS.Provider != "openai" {
		return errors.New("配音方式无效。")
	}
	if c.TTS.Voice == "" || len(c.TTS.Voice) > 100 {
		return errors.New("请填写配音音色。")
	}
	return nil
}
