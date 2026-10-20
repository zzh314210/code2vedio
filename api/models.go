package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"sort"
	"strings"
	"time"
)

// Resolve and validate at dial time, then connect to the checked address directly.
// The original URL retains its TLS hostname; redirects and environment proxies are disabled.
func publicModelClient() *http.Client {
	return &http.Client{
		Timeout:       15 * time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
		Transport: &http.Transport{
			TLSHandshakeTimeout:   8 * time.Second,
			ResponseHeaderTimeout: 10 * time.Second,
			IdleConnTimeout:       30 * time.Second,
			MaxIdleConns:          10,
			DialContext: func(ctx context.Context, network, address string) (net.Conn, error) {
				host, port, err := net.SplitHostPort(address)
				if err != nil || port != "443" {
					return nil, errors.New("only public HTTPS endpoints are allowed")
				}
				ips, err := net.DefaultResolver.LookupIPAddr(ctx, host)
				if err != nil || len(ips) == 0 {
					return nil, errors.New("cannot resolve model service")
				}
				for _, ip := range ips {
					if !publicIP(ip.IP) {
						return nil, errors.New("private model service address refused")
					}
				}
				var last error
				for _, ip := range ips {
					conn, e := (&net.Dialer{Timeout: 5 * time.Second}).DialContext(ctx, "tcp", net.JoinHostPort(ip.IP.String(), port))
					if e == nil {
						return conn, nil
					}
					last = e
				}
				return nil, last
			},
		},
	}
}

func (s *Server) listModels(w http.ResponseWriter, r *http.Request) {
	u := current(r)
	if err := s.Store.limit("model-list:"+u.ID, 15, 60); err != nil {
		fail(w, 429, "获取过于频繁，请稍后重试。")
		return
	}
	var d struct {
		Role     string `json:"role"`
		BaseURL  string `json:"base_url"`
		APIKey   string `json:"api_key"`
		ClearKey bool   `json:"clear_key"`
	}
	if !decode(w, r, &d) {
		return
	}
	if d.Role != "text" && d.Role != "vision" && d.Role != "tts" {
		fail(w, 422, "请选择内容生成、视觉审核或配音服务。")
		return
	}
	d.BaseURL = strings.TrimRight(strings.TrimSpace(d.BaseURL), "/")
	d.APIKey = strings.TrimSpace(d.APIKey)
	if len(d.BaseURL) > 500 || len(d.APIKey) > 2048 || strings.ContainsAny(d.APIKey, "\r\n") || strings.Contains(d.APIKey, "${") {
		fail(w, 422, "请检查接口地址和密钥格式。")
		return
	}
	if err := validateEndpoint(d.BaseURL); err != nil {
		fail(w, 422, err.Error())
		return
	}
	config, err := s.Store.config(u.ID)
	if err != nil {
		s.internal(w, err)
		return
	}
	saved := config.Text
	if d.Role == "vision" {
		saved = config.Vision
	}
	if d.Role == "tts" {
		saved = config.TTS
	}
	if d.ClearKey {
		d.APIKey = ""
	} else if d.APIKey == "" && d.BaseURL == saved.BaseURL {
		d.APIKey = saved.APIKey
	}
	if d.APIKey == "" {
		fail(w, 422, "请先填写此服务的密钥；更换接口地址后需要重新填写。")
		return
	}
	s.fetchModels(w, r, Channel{BaseURL: d.BaseURL, APIKey: d.APIKey})
}
func (s *Server) fetchModels(w http.ResponseWriter, r *http.Request, d Channel) {
	upstream, err := http.NewRequestWithContext(r.Context(), http.MethodGet, d.BaseURL+"/models", nil)
	if err != nil {
		fail(w, 422, "接口地址格式不正确。")
		return
	}
	upstream.Header.Set("Authorization", "Bearer "+d.APIKey)
	upstream.Header.Set("Accept", "application/json")
	response, err := s.ModelsClient.Do(upstream)
	if err != nil {
		fail(w, 502, "暂时无法连接模型服务，请检查地址后重试，也可以手动填写模型名称。")
		return
	}
	defer response.Body.Close()
	if response.StatusCode == 401 || response.StatusCode == 403 {
		fail(w, 422, "服务商未接受此密钥，请检查密钥是否有效、是否有模型列表权限。")
		return
	}
	if response.StatusCode == 404 || response.StatusCode == 405 {
		fail(w, 422, "此接口未提供模型列表，请按服务商说明手动填写模型名称。")
		return
	}
	if response.StatusCode == 429 {
		fail(w, 429, "模型服务请求过于频繁，请稍后重试。")
		return
	}
	if response.StatusCode != 200 {
		fail(w, 502, "服务商暂时未能返回模型列表，请稍后重试或手动填写模型名称。")
		return
	}
	const maxBody = 2 * 1024 * 1024
	body, err := io.ReadAll(io.LimitReader(response.Body, maxBody+1))
	if err != nil || len(body) > maxBody {
		fail(w, 502, "模型列表读取失败或过大，请手动填写模型名称。")
		return
	}
	models, err := parseModels(body)
	if err != nil {
		fail(w, 422, "服务商返回的列表格式不兼容，请手动填写模型名称。")
		return
	}
	sort.Strings(models)
	reply(w, 200, map[string]any{"models": models})
}

// Accept the common upstream list shapes also handled by sub2api's catalog sync.
func parseModels(body []byte) ([]string, error) {
	var envelope struct {
		Data   []json.RawMessage `json:"data"`
		Models []json.RawMessage `json:"models"`
	}
	var entries []json.RawMessage
	if json.Unmarshal(body, &envelope) == nil && (envelope.Data != nil || envelope.Models != nil) {
		entries = append(envelope.Data, envelope.Models...)
	} else if json.Unmarshal(body, &entries) != nil || entries == nil {
		return nil, errors.New("invalid model catalog")
	}
	seen := map[string]bool{}
	models := []string{}
	for _, raw := range entries {
		var id string
		if json.Unmarshal(raw, &id) != nil {
			var entry struct {
				ID   string `json:"id"`
				Name string `json:"name"`
			}
			if json.Unmarshal(raw, &entry) != nil {
				continue
			}
			id = entry.ID
			if id == "" {
				id = entry.Name
			}
		}
		id = strings.TrimSpace(id)
		if id == "" || len(id) > 150 || strings.ContainsAny(id, "\r\n\x00") || seen[id] {
			continue
		}
		seen[id] = true
		models = append(models, id)
	}
	return models, nil
}
