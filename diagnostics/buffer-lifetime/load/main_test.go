package main

import (
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

type responseTransport struct{ response *http.Response }

func (tr responseTransport) RoundTrip(*http.Request) (*http.Response, error) { return tr.response, nil }
func TestRequestValidationRejectsFalseWins(t *testing.T) {
	for _, tc := range []struct {
		name, body       string
		status, protocol int
		wantError        bool
	}{
		{"valid", "hello, world\n", 200, 1, false},
		{"bad status", "hello, world\n", 503, 1, true},
		{"wrong body", "truncated", 200, 1, true},
		{"wrong protocol", "hello, world\n", 200, 2, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			cl := &http.Client{Transport: responseTransport{&http.Response{StatusCode: tc.status, ProtoMajor: tc.protocol, Proto: "test", Body: io.NopCloser(strings.NewReader(tc.body))}}}
			var hs, hsTime atomic.Int64
			sample := one(cl, config{protocol: "h1", workload: "small"}, nil, time.Now().Add(-time.Millisecond), &hs, &hsTime)
			if (sample.err != nil) != tc.wantError {
				t.Fatalf("error=%v", sample.err)
			}
			if sample.latency < time.Millisecond {
				t.Fatal("scheduled queue delay was excluded")
			}
		})
	}
}
func TestChunkedUploadDoesNotAdvertiseContentLength(t *testing.T) {
	req := request(config{workload: "chunked"}, []byte("payload"))
	if req.ContentLength != -1 {
		t.Fatalf("ContentLength=%d", req.ContentLength)
	}
	b, err := io.ReadAll(req.Body)
	if err != nil || string(b) != "payload" {
		t.Fatalf("body=%q err=%v", b, err)
	}
}
