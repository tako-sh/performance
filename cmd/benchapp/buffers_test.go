package main

import (
	"bytes"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestBufferTransfers(t *testing.T) {
	mux := http.NewServeMux()
	registerBufferEndpoints(mux)
	for _, tc := range []struct {
		path   string
		body   []byte
		status int
		length int
	}{
		{"/buffer/upload", transferPayload, 200, 3},
		{"/buffer/upload", transferPayload[:10], 400, 17},
		{"/buffer/upload", bytes.Repeat([]byte{'B'}, transferSize), 400, 17},
		{"/buffer/download", nil, 200, transferSize},
	} {
		w := httptest.NewRecorder()
		mux.ServeHTTP(w, httptest.NewRequest("POST", tc.path, bytes.NewReader(tc.body)))
		if w.Code != tc.status || w.Body.Len() != tc.length {
			t.Fatalf("%s: %d %d", tc.path, w.Code, w.Body.Len())
		}
	}
}
func TestStreamWaitsForReleaseAfterUpload(t *testing.T) {
	mux := http.NewServeMux()
	registerBufferEndpoints(mux)
	server := httptest.NewServer(mux)
	defer server.Close()
	response, err := http.Post(server.URL+"/buffer/stream", "application/octet-stream", bytes.NewReader(transferPayload[:128*1024]))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	ready := make([]byte, 6)
	if _, err := io.ReadFull(response.Body, ready); err != nil {
		t.Fatal(err)
	}
	if string(ready) != "ready\n" {
		t.Fatalf("unexpected initial bytes %q", ready)
	}
	released, err := http.Get(server.URL + "/buffer/release")
	if err != nil {
		t.Fatal(err)
	}
	released.Body.Close()
	tail, err := io.ReadAll(response.Body)
	if err != nil || string(tail) != "done\n" {
		t.Fatalf("tail %q %v", tail, err)
	}
}
