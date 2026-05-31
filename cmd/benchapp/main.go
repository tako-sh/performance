package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const internalTokenHeader = "x-tako-internal-token"

type bootstrap struct {
	Token string `json:"token"`
}

type serverConfig struct {
	appName      string
	instanceID   string
	version      string
	host         string
	port         string
	internalAuth string
	startedAt    time.Time
}

func main() {
	cfg := serverConfig{
		appName:    getenvDefault("TAKO_APP_NAME", "bench-http"),
		version:    os.Getenv("TAKO_BUILD"),
		host:       getenvDefault("HOST", "127.0.0.1"),
		port:       getenvDefault("PORT", "9101"),
		instanceID: parseInstanceID(os.Args[1:]),
		startedAt:  time.Now(),
	}
	if cfg.port == "0" {
		cfg.internalAuth = readBootstrapToken()
	}

	addr := net.JoinHostPort(cfg.host, cfg.port)
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		fmt.Fprintf(os.Stderr, "listen %s: %v\n", addr, err)
		os.Exit(1)
	}
	if cfg.port == "0" {
		if tcpAddr, ok := ln.Addr().(*net.TCPAddr); ok {
			signalReady(tcpAddr.Port)
		}
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/", cfg.handleRoot)
	mux.HandleFunc("/plaintext", cfg.handlePlaintext)
	mux.HandleFunc("/json", cfg.handleJSON)
	mux.HandleFunc("/sleep", cfg.handleSleep)
	mux.HandleFunc("/pid", cfg.handlePID)

	server := &http.Server{
		Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if normalizeHost(r.Host) == internalHost(cfg.appName) {
				cfg.handleInternal(w, r)
				return
			}
			mux.ServeHTTP(w, r)
		}),
	}
	if err := server.Serve(ln); err != nil && !errors.Is(err, http.ErrServerClosed) {
		fmt.Fprintf(os.Stderr, "serve: %v\n", err)
		os.Exit(1)
	}
}

func (cfg serverConfig) handleRoot(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("content-type", "text/html; charset=utf-8")
	_, _ = io.WriteString(w, "<!doctype html><html><body><h1>Tako performance benchmark</h1></body></html>")
}

func (cfg serverConfig) handlePlaintext(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("content-type", "text/plain; charset=utf-8")
	w.Header().Set("content-length", "13")
	_, _ = io.WriteString(w, "hello, world\n")
}

func (cfg serverConfig) handleJSON(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("content-type", "application/json")
	_, _ = io.WriteString(w, `{"message":"hello","ok":true}`+"\n")
}

func (cfg serverConfig) handleSleep(w http.ResponseWriter, r *http.Request) {
	ms, _ := strconv.Atoi(r.URL.Query().Get("ms"))
	if ms < 0 {
		ms = 0
	}
	if ms > 1000 {
		ms = 1000
	}
	time.Sleep(time.Duration(ms) * time.Millisecond)
	cfg.handlePlaintext(w, r)
}

func (cfg serverConfig) handlePID(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("content-type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"pid":        os.Getpid(),
		"instance":   cfg.instanceID,
		"version":    cfg.version,
		"app":        cfg.appName,
		"uptime_sec": int64(time.Since(cfg.startedAt).Seconds()),
	})
}

func (cfg serverConfig) handleInternal(w http.ResponseWriter, r *http.Request) {
	if cfg.internalAuth != "" && r.Header.Get(internalTokenHeader) != cfg.internalAuth {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	if r.Method != http.MethodGet || r.URL.Path != "/status" {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("content-type", "application/json")
	if cfg.internalAuth != "" {
		w.Header().Set(internalTokenHeader, cfg.internalAuth)
	}
	_ = json.NewEncoder(w).Encode(map[string]any{
		"status":         "healthy",
		"instance_id":    cfg.instanceID,
		"version":        cfg.version,
		"pid":            os.Getpid(),
		"uptime_seconds": int64(time.Since(cfg.startedAt).Seconds()),
	})
}

func parseInstanceID(args []string) string {
	for i := 0; i < len(args); i++ {
		if args[i] == "--instance" && i+1 < len(args) {
			return args[i+1]
		}
	}
	return ""
}

func getenvDefault(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}

func readBootstrapToken() string {
	file := os.NewFile(3, "tako-bootstrap")
	if file == nil {
		return ""
	}
	defer file.Close()

	payload, err := io.ReadAll(file)
	if err != nil {
		if errors.Is(err, syscall.EBADF) {
			return ""
		}
		fmt.Fprintf(os.Stderr, "read fd3 bootstrap: %v\n", err)
		os.Exit(1)
	}
	var b bootstrap
	if err := json.Unmarshal(payload, &b); err != nil {
		fmt.Fprintf(os.Stderr, "parse fd3 bootstrap: %v\n", err)
		os.Exit(1)
	}
	return b.Token
}

func signalReady(port int) {
	var st syscall.Stat_t
	if err := syscall.Fstat(4, &st); err != nil {
		return
	}
	if st.Mode&syscall.S_IFMT != syscall.S_IFIFO {
		return
	}
	ready := os.NewFile(4, "tako-ready")
	if ready == nil {
		return
	}
	defer ready.Close()
	_, _ = fmt.Fprintf(ready, "%d\n", port)
}

func normalizeHost(host string) string {
	host = strings.ToLower(strings.TrimSpace(host))
	if host == "" {
		return ""
	}
	if strings.HasPrefix(host, "[") {
		if end := strings.Index(host, "]"); end >= 0 {
			return host[1:end]
		}
	}
	if h, _, err := net.SplitHostPort(host); err == nil {
		return h
	}
	if idx := strings.LastIndex(host, ":"); idx >= 0 {
		return host[:idx]
	}
	return host
}

func internalHost(appName string) string {
	appName = strings.ToLower(strings.TrimSpace(appName))
	if base, _, ok := strings.Cut(appName, "/"); ok {
		appName = base
	}
	if appName == "" {
		appName = "app"
	}
	return appName + ".tako"
}
