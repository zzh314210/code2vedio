package main

import "testing"

func TestRemovedSearchAndLinkIngestionDoNotReachWorker(t *testing.T) {
	_, s := fixture(t)
	_, cookie := registered(t, s, "uploads-only")
	for _, route := range []string{"/api/sources", "/api/sources/search?query=test", "/api/sources/ingest", "/api/sources/old-id"} {
		for _, method := range []string{"GET", "POST"} {
			if r := call(t, s, method, route, nil, cookie, ""); r.Code != 404 {
				t.Fatal(method, route, r.Code)
			}
		}
	}
	for _, field := range []string{"reference_urls", "source_ids"} {
		r := call(t, s, "POST", "/api/jobs", map[string]any{"prompt": "teach compound interest", field: []string{"https://example.com"}}, cookie, "")
		if r.Code != 422 {
			t.Fatal(field, r.Code, r.Body.String())
		}
	}
}
