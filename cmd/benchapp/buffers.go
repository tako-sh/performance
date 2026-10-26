package main

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"sync"
)

const transferSize = 1 << 20

var transferPayload = bytes.Repeat([]byte{'A'}, transferSize)

type payloadCheck struct {
	bytes   int64
	invalid bool
}

func (v *payloadCheck) Write(p []byte) (int, error) {
	v.bytes += int64(len(p))
	v.invalid = v.invalid || bytes.Count(p, []byte{'A'}) != len(p)
	return len(p), nil
}

func registerBufferEndpoints(mux *http.ServeMux) {
	gate := make(chan struct{})
	var release sync.Once
	upload := func(w http.ResponseWriter, r *http.Request, want int64) bool {
		var check payloadCheck
		_, err := io.Copy(&check, io.LimitReader(r.Body, want+1))
		if err != nil || check.invalid || check.bytes != want {
			http.Error(w, "incorrect upload", http.StatusBadRequest)
			return false
		}
		return true
	}
	mux.HandleFunc("/buffer/upload", func(w http.ResponseWriter, r *http.Request) {
		if upload(w, r, transferSize) {
			fmt.Fprint(w, "ok\n")
		}
	})
	mux.HandleFunc("/buffer/download", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", strconv.Itoa(transferSize))
		w.Write(transferPayload)
	})
	mux.HandleFunc("/buffer/stream", func(w http.ResponseWriter, r *http.Request) {
		if !upload(w, r, 128*1024) {
			return
		}
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprint(w, "ready\n")
		w.(http.Flusher).Flush()
		select {
		case <-gate:
			fmt.Fprint(w, "done\n")
		case <-r.Context().Done():
		}
	})
	mux.HandleFunc("/buffer/release", func(w http.ResponseWriter, r *http.Request) {
		release.Do(func() { close(gate) })
		fmt.Fprint(w, "ok\n")
	})
}
