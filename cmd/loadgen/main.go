package main

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"math"
	"net"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type result struct {
	Name          string             `json:"name"`
	Method        string             `json:"method"`
	URL           string             `json:"url"`
	HostHeader    string             `json:"host_header,omitempty"`
	ServerName    string             `json:"server_name,omitempty"`
	SourceIPCount int                `json:"source_ip_count,omitempty"`
	DurationSec   float64            `json:"duration_sec"`
	Concurrency   int                `json:"concurrency"`
	Requests      int64              `json:"requests"`
	Errors        int64              `json:"errors"`
	Bytes         int64              `json:"bytes"`
	RequestsPerS  float64            `json:"requests_per_sec"`
	BytesPerS     float64            `json:"bytes_per_sec"`
	LatencyMillis map[string]float64 `json:"latency_ms"`
	StatusCounts  map[string]int64   `json:"status_counts"`
	ErrorKinds    map[string]int64   `json:"error_kinds,omitempty"`
	StartedAt     string             `json:"started_at"`
}

func main() {
	var (
		name        = flag.String("name", "", "benchmark name")
		targetURL   = flag.String("url", "", "target URL")
		method      = flag.String("method", http.MethodGet, "HTTP method")
		body        = flag.String("body", "", "request body")
		contentType = flag.String("content-type", "", "Content-Type header")
		hostHeader  = flag.String("host", "", "Host header override")
		serverName  = flag.String("sni", "", "TLS server name override")
		resolve     = flag.String("resolve", "", "host:port:ip mapping")
		sourceIPs   = flag.String("source-ips", "", "comma-separated local source IPs for outbound TCP connections")
		duration    = flag.Duration("duration", 30*time.Second, "measurement duration")
		warmup      = flag.Duration("warmup", 5*time.Second, "warmup duration")
		concurrency = flag.Int("concurrency", 100, "concurrent workers")
		insecure    = flag.Bool("insecure", false, "skip TLS verification")
	)
	flag.Parse()
	if *targetURL == "" {
		fmt.Fprintln(os.Stderr, "-url is required")
		os.Exit(2)
	}
	*method = strings.ToUpper(strings.TrimSpace(*method))
	if *method == "" {
		fmt.Fprintln(os.Stderr, "-method must not be empty")
		os.Exit(2)
	}
	parsedSourceIPs, err := parseSourceIPs(*sourceIPs)
	if err != nil {
		fmt.Fprintf(os.Stderr, "invalid -source-ips: %v\n", err)
		os.Exit(2)
	}

	transport := &http.Transport{
		Proxy:               http.ProxyFromEnvironment,
		MaxIdleConns:        *concurrency * 2,
		MaxIdleConnsPerHost: *concurrency * 2,
		IdleConnTimeout:     90 * time.Second,
		ForceAttemptHTTP2:   false,
		TLSClientConfig: &tls.Config{
			InsecureSkipVerify: *insecure,
			ServerName:         *serverName,
			MinVersion:         tls.VersionTLS12,
		},
	}
	if *resolve != "" || len(parsedSourceIPs) > 0 {
		host, port, ip, err := parseResolve(*resolve)
		if *resolve != "" && err != nil {
			fmt.Fprintf(os.Stderr, "invalid -resolve: %v\n", err)
			os.Exit(2)
		}
		var dialCounter uint64
		transport.DialContext = func(ctx context.Context, network, addr string) (net.Conn, error) {
			if *resolve != "" && addr == net.JoinHostPort(host, port) {
				addr = net.JoinHostPort(ip, port)
			}
			dialer := &net.Dialer{Timeout: 10 * time.Second, KeepAlive: 30 * time.Second}
			if len(parsedSourceIPs) > 0 {
				idx := atomic.AddUint64(&dialCounter, 1) - 1
				dialer.LocalAddr = &net.TCPAddr{IP: parsedSourceIPs[int(idx)%len(parsedSourceIPs)]}
			}
			return dialer.DialContext(ctx, network, addr)
		}
	}

	client := &http.Client{Transport: transport, Timeout: 10 * time.Second}
	if *warmup > 0 {
		run(client, runConfig{
			name:        *name,
			url:         *targetURL,
			method:      *method,
			body:        []byte(*body),
			contentType: *contentType,
			hostHeader:  *hostHeader,
			sourceIPs:   len(parsedSourceIPs),
			duration:    *warmup,
			concurrency: *concurrency,
		})
	}
	transport.CloseIdleConnections()
	res := run(client, runConfig{
		name:        *name,
		url:         *targetURL,
		method:      *method,
		body:        []byte(*body),
		contentType: *contentType,
		hostHeader:  *hostHeader,
		serverName:  *serverName,
		sourceIPs:   len(parsedSourceIPs),
		duration:    *duration,
		concurrency: *concurrency,
	})

	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(res); err != nil {
		fmt.Fprintf(os.Stderr, "write result: %v\n", err)
		os.Exit(1)
	}
}

type runConfig struct {
	name        string
	url         string
	method      string
	body        []byte
	contentType string
	hostHeader  string
	serverName  string
	sourceIPs   int
	duration    time.Duration
	concurrency int
}

func run(client *http.Client, cfg runConfig) result {
	startedAt := time.Now()
	deadline := startedAt.Add(cfg.duration)
	var requests, errors, responseBytes int64
	var mu sync.Mutex
	latencies := make([]int64, 0, 1024)
	statusCounts := map[string]int64{}
	errorKinds := map[string]int64{}

	var wg sync.WaitGroup
	for i := 0; i < cfg.concurrency; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for time.Now().Before(deadline) {
				req, err := http.NewRequest(cfg.method, cfg.url, bytes.NewReader(cfg.body))
				if err != nil {
					recordError(&mu, errorKinds, "build_request")
					atomic.AddInt64(&errors, 1)
					continue
				}
				if cfg.hostHeader != "" {
					req.Host = cfg.hostHeader
				}
				if cfg.contentType != "" {
					req.Header.Set("Content-Type", cfg.contentType)
				}
				t0 := time.Now()
				resp, err := client.Do(req)
				elapsed := time.Since(t0).Nanoseconds()
				if err != nil {
					recordError(&mu, errorKinds, classifyError(err))
					atomic.AddInt64(&errors, 1)
					continue
				}
				n, readErr := io.Copy(io.Discard, resp.Body)
				closeErr := resp.Body.Close()
				if readErr != nil || closeErr != nil {
					recordError(&mu, errorKinds, "read_response")
					atomic.AddInt64(&errors, 1)
				}
				atomic.AddInt64(&requests, 1)
				atomic.AddInt64(&responseBytes, n)
				mu.Lock()
				latencies = append(latencies, elapsed)
				statusCounts[strconv.Itoa(resp.StatusCode)]++
				mu.Unlock()
			}
		}()
	}
	wg.Wait()

	elapsedSec := time.Since(startedAt).Seconds()
	reqs := atomic.LoadInt64(&requests)
	totalBytes := atomic.LoadInt64(&responseBytes)
	res := result{
		Name:          cfg.name,
		Method:        cfg.method,
		URL:           cfg.url,
		HostHeader:    cfg.hostHeader,
		ServerName:    cfg.serverName,
		SourceIPCount: cfg.sourceIPs,
		DurationSec:   elapsedSec,
		Concurrency:   cfg.concurrency,
		Requests:      reqs,
		Errors:        atomic.LoadInt64(&errors),
		Bytes:         totalBytes,
		RequestsPerS:  float64(reqs) / elapsedSec,
		BytesPerS:     float64(totalBytes) / elapsedSec,
		LatencyMillis: latencySummary(latencies),
		StatusCounts:  statusCounts,
		ErrorKinds:    errorKinds,
		StartedAt:     startedAt.UTC().Format(time.RFC3339),
	}
	if len(res.ErrorKinds) == 0 {
		res.ErrorKinds = nil
	}
	return res
}

func latencySummary(values []int64) map[string]float64 {
	out := map[string]float64{
		"min":  0,
		"mean": 0,
		"p50":  0,
		"p90":  0,
		"p95":  0,
		"p99":  0,
		"max":  0,
	}
	if len(values) == 0 {
		return out
	}
	sort.Slice(values, func(i, j int) bool { return values[i] < values[j] })
	var sum int64
	for _, v := range values {
		sum += v
	}
	out["min"] = nsToMs(values[0])
	out["mean"] = nsToMs(sum / int64(len(values)))
	out["p50"] = nsToMs(percentile(values, 0.50))
	out["p90"] = nsToMs(percentile(values, 0.90))
	out["p95"] = nsToMs(percentile(values, 0.95))
	out["p99"] = nsToMs(percentile(values, 0.99))
	out["max"] = nsToMs(values[len(values)-1])
	return out
}

func percentile(values []int64, p float64) int64 {
	if len(values) == 0 {
		return 0
	}
	idx := int(math.Ceil(p*float64(len(values)))) - 1
	if idx < 0 {
		idx = 0
	}
	if idx >= len(values) {
		idx = len(values) - 1
	}
	return values[idx]
}

func nsToMs(ns int64) float64 {
	return float64(ns) / float64(time.Millisecond)
}

func recordError(mu *sync.Mutex, counts map[string]int64, kind string) {
	mu.Lock()
	counts[kind]++
	mu.Unlock()
}

func classifyError(err error) string {
	text := err.Error()
	switch {
	case strings.Contains(text, "connection refused"):
		return "connection_refused"
	case strings.Contains(text, "timeout"):
		return "timeout"
	case strings.Contains(text, "connection reset"):
		return "connection_reset"
	case strings.Contains(text, "EOF"):
		return "eof"
	default:
		return "request_error"
	}
}

func parseResolve(value string) (host, port, ip string, err error) {
	if strings.TrimSpace(value) == "" {
		return "", "", "", nil
	}
	parts := strings.Split(value, ":")
	if len(parts) != 3 {
		return "", "", "", fmt.Errorf("expected host:port:ip")
	}
	if net.ParseIP(parts[2]) == nil {
		return "", "", "", fmt.Errorf("invalid IP %q", parts[2])
	}
	if _, err := strconv.Atoi(parts[1]); err != nil {
		return "", "", "", fmt.Errorf("invalid port %q", parts[1])
	}
	return parts[0], parts[1], parts[2], nil
}

func parseSourceIPs(value string) ([]net.IP, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil, nil
	}
	parts := strings.Split(value, ",")
	ips := make([]net.IP, 0, len(parts))
	for _, part := range parts {
		ip := net.ParseIP(strings.TrimSpace(part))
		if ip == nil {
			return nil, fmt.Errorf("invalid IP %q", part)
		}
		ips = append(ips, ip)
	}
	return ips, nil
}
