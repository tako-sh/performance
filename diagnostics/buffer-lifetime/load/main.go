// The client verifies protocol, status, and payload and reports latency from the
// scheduled arrival time when running at a fixed rate (including queue delay).
package main

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptrace"
	"os"
	"sort"
	"sync"
	"sync/atomic"
	"time"
)

type config struct {
	protocol, workload, phase string
	workers, rate             int
	duration, warmup          time.Duration
	churn                     bool
}
type result struct {
	Requests        int                `json:"requests"`
	Errors          int                `json:"errors"`
	Duration        float64            `json:"duration_seconds"`
	RPS             float64            `json:"requests_per_second"`
	PayloadBytes    int64              `json:"payload_bytes"`
	Latency         map[string]float64 `json:"latency_ms"`
	Handshakes      int64              `json:"handshakes"`
	HandshakeMillis float64            `json:"handshake_total_ms"`
	Protocol        string             `json:"protocol"`
	Workload        string             `json:"workload"`
	ErrorSamples    []string           `json:"error_samples"`
}
type sample struct {
	latency time.Duration
	bytes   int64
	err     error
}
type validation struct {
	n       int64
	invalid bool
}

func (v *validation) Write(p []byte) (int, error) {
	v.n += int64(len(p))
	v.invalid = v.invalid || bytes.Count(p, []byte{'A'}) != len(p)
	return len(p), nil
}
func phase(path, state string) {
	if path != "" {
		b, _ := json.Marshal(map[string]string{"phase": state})
		tmp := path + ".tmp"
		if err := os.WriteFile(tmp, b, 0644); err != nil {
			panic(err)
		}
		if err := os.Rename(tmp, path); err != nil {
			panic(err)
		}
	}
}
func client(c config) (*http.Client, *http.Transport) {
	var dials atomic.Uint64
	tr := &http.Transport{MaxConnsPerHost: c.workers, MaxIdleConns: c.workers, MaxIdleConnsPerHost: c.workers, DisableKeepAlives: c.churn,
		ForceAttemptHTTP2: c.protocol == "h2", TLSClientConfig: &tls.Config{InsecureSkipVerify: true, ServerName: "bench.test", MinVersion: tls.VersionTLS12},
		DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
			ip := net.IPv4(127, 0, 0, byte(2+(dials.Add(1)-1)%16))
			d := net.Dialer{Timeout: 10 * time.Second, LocalAddr: &net.TCPAddr{IP: ip}}
			return d.DialContext(ctx, network, addr)
		}}
	return &http.Client{Transport: tr, Timeout: 60 * time.Second}, tr
}
func request(c config, payload []byte) *http.Request {
	path := "/plaintext"
	method := "GET"
	var body io.Reader
	switch c.workload {
	case "upload", "chunked":
		path = "/buffer/upload"
		method = "POST"
		body = bytes.NewReader(payload)
	case "download":
		path = "/buffer/download"
	case "stream":
		path = "/buffer/stream"
		method = "POST"
		body = bytes.NewReader(payload[:128*1024])
	}
	req, _ := http.NewRequest(method, "https://127.0.0.1:18443"+path, body)
	req.Host = "bench.test"
	if c.workload == "chunked" {
		req.ContentLength = -1
	}
	return req
}
func checkResponse(resp *http.Response, c config) error {
	if resp.StatusCode != 200 {
		return fmt.Errorf("status %d", resp.StatusCode)
	}
	want := 1
	if c.protocol == "h2" {
		want = 2
	}
	if resp.ProtoMajor != want {
		return fmt.Errorf("protocol %s", resp.Proto)
	}
	return nil
}
func one(cl *http.Client, c config, payload []byte, scheduled time.Time, hs *atomic.Int64, hsTime *atomic.Int64) sample {
	req := request(c, payload)
	var start time.Time
	trace := &httptrace.ClientTrace{TLSHandshakeStart: func() { start = time.Now() }, TLSHandshakeDone: func(_ tls.ConnectionState, _ error) { hs.Add(1); hsTime.Add(time.Since(start).Nanoseconds()) }}
	req = req.WithContext(httptrace.WithClientTrace(req.Context(), trace))
	resp, err := cl.Do(req)
	var n int64
	if err == nil {
		err = checkResponse(resp, c)
		if c.workload == "download" {
			var v validation
			_, readErr := io.Copy(&v, resp.Body)
			n = v.n
			if readErr != nil {
				err = readErr
			} else if v.invalid || n != 1<<20 {
				err = fmt.Errorf("incorrect download: %d bytes", n)
			}
		} else {
			b, readErr := io.ReadAll(resp.Body)
			want := "hello, world\n"
			if c.workload == "upload" || c.workload == "chunked" {
				want = "ok\n"
				n = int64(len(payload))
			}
			if readErr != nil {
				err = readErr
			} else if string(b) != want {
				err = fmt.Errorf("incorrect response: %d bytes", len(b))
			}
		}
		resp.Body.Close()
	}
	return sample{time.Since(scheduled), n, err}
}
func run(cl *http.Client, c config, duration time.Duration) result {
	payload := bytes.Repeat([]byte{'A'}, 1<<20)
	var hs, hsTime atomic.Int64
	output := make(chan sample, c.workers*2)
	var wg sync.WaitGroup
	start := time.Now()
	deadline := start.Add(duration)
	var arrivals chan time.Time
	if c.rate > 0 {
		arrivals = make(chan time.Time, c.workers*2)
		go func() {
			defer close(arrivals)
			for i := 0; ; i++ {
				at := start.Add(time.Duration(float64(i) * float64(time.Second) / float64(c.rate)))
				if !at.Before(deadline) {
					return
				}
				if wait := time.Until(at); wait > 0 {
					time.Sleep(wait)
				}
				arrivals <- at
			}
		}()
	}
	for worker := 0; worker < c.workers; worker++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if arrivals != nil {
				for at := range arrivals {
					output <- one(cl, c, payload, at, &hs, &hsTime)
				}
			} else {
				for time.Now().Before(deadline) {
					output <- one(cl, c, payload, time.Now(), &hs, &hsTime)
				}
			}
		}()
	}
	go func() { wg.Wait(); close(output) }()
	r := result{Protocol: c.protocol, Workload: c.workload, Latency: map[string]float64{}}
	latencies := make([]float64, 0, 100000)
	for s := range output {
		r.Requests++
		r.PayloadBytes += s.bytes
		latencies = append(latencies, float64(s.latency)/float64(time.Millisecond))
		if s.err != nil {
			r.Errors++
			if len(r.ErrorSamples) < 5 {
				r.ErrorSamples = append(r.ErrorSamples, s.err.Error())
			}
		}
	}
	r.Duration = time.Since(start).Seconds()
	r.RPS = float64(r.Requests-r.Errors) / r.Duration
	r.Handshakes = hs.Load()
	r.HandshakeMillis = float64(hsTime.Load()) / 1e6
	sort.Float64s(latencies)
	if len(latencies) > 0 {
		for label, q := range map[string]float64{"p50": .50, "p95": .95, "p99": .99} {
			r.Latency[label] = latencies[int(float64(len(latencies)-1)*q)]
		}
	}
	return r
}
func stream(cl *http.Client, c config) result {
	payload := bytes.Repeat([]byte{'A'}, 1<<20)
	ready := make(chan error, c.workers)
	done := make(chan error, c.workers)
	slots := make(chan struct{}, 32)
	start := time.Now()
	for i := 0; i < c.workers; i++ {
		slots <- struct{}{}
		go func() {
			resp, err := cl.Do(request(c, payload))
			if err == nil {
				err = checkResponse(resp, c)
			}
			if err == nil {
				b := make([]byte, 6)
				_, err = io.ReadFull(resp.Body, b)
				if err == nil && string(b) != "ready\n" {
					err = fmt.Errorf("incorrect stream prefix")
				}
			}
			ready <- err
			<-slots
			if err == nil {
				tail, e := io.ReadAll(resp.Body)
				err = e
				if err == nil && string(tail) != "done\n" {
					err = fmt.Errorf("incorrect stream suffix")
				}
			}
			if resp != nil {
				resp.Body.Close()
			}
			done <- err
		}()
	}
	r := result{Protocol: c.protocol, Workload: c.workload, Latency: map[string]float64{}}
	for i := 0; i < c.workers; i++ {
		if err := <-ready; err != nil {
			r.Errors++
			if len(r.ErrorSamples) < 5 {
				r.ErrorSamples = append(r.ErrorSamples, err.Error())
			}
		}
	}
	if r.Errors == 0 {
		phase(c.phase, "holding")
		time.Sleep(c.duration)
	}
	phase(c.phase, "releasing")
	req, _ := http.NewRequest("GET", "https://127.0.0.1:18443/buffer/release", nil)
	req.Host = "bench.test"
	// Use a separate transport: the streaming workers may occupy every H1 slot.
	control, tr := client(c)
	resp, err := control.Do(req)
	if err != nil {
		r.Errors++
	} else {
		io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
		if resp.StatusCode != 200 {
			r.Errors++
		}
	}
	tr.CloseIdleConnections()
	for i := 0; i < c.workers; i++ {
		r.Requests++
		if err := <-done; err != nil {
			r.Errors++
			if len(r.ErrorSamples) < 5 {
				r.ErrorSamples = append(r.ErrorSamples, err.Error())
			}
		}
	}
	r.Duration = time.Since(start).Seconds()
	r.PayloadBytes = int64(r.Requests) * 128 * 1024
	return r
}
func main() {
	var c config
	flag.StringVar(&c.protocol, "protocol", "h1", "h1 or h2")
	flag.StringVar(&c.workload, "workload", "small", "small, upload, chunked, download, stream")
	flag.StringVar(&c.phase, "phase-file", "", "phase output")
	flag.IntVar(&c.workers, "workers", 64, "workers")
	flag.IntVar(&c.rate, "rate", 0, "scheduled requests/s; zero means closed loop")
	flag.DurationVar(&c.duration, "duration", 15*time.Second, "measurement/hold duration")
	flag.DurationVar(&c.warmup, "warmup", 3*time.Second, "warmup")
	flag.BoolVar(&c.churn, "churn", false, "disable connection reuse")
	flag.Parse()
	if c.workers < 1 || c.duration <= 0 || c.rate < 0 || (c.protocol != "h1" && c.protocol != "h2") {
		panic("invalid workload configuration")
	}
	cl, tr := client(c)
	defer tr.CloseIdleConnections()
	var r result
	phase(c.phase, "warmup")
	if c.workload == "stream" {
		r = stream(cl, c)
	} else {
		if c.warmup > 0 {
			warm := run(cl, c, c.warmup)
			if warm.Errors > 0 {
				json.NewEncoder(os.Stdout).Encode(warm)
				os.Exit(1)
			}
		}
		if c.phase != "" {
			phase(c.phase, "ready")
			deadline := time.Now().Add(10 * time.Second)
			for {
				if _, err := os.Stat(c.phase + ".start"); err == nil {
					break
				}
				if time.Now().After(deadline) {
					panic("sampler did not acknowledge measurement")
				}
				time.Sleep(time.Millisecond)
			}
		}
		phase(c.phase, "measuring")
		r = run(cl, c, c.duration)
	}
	phase(c.phase, "done")
	json.NewEncoder(os.Stdout).Encode(r)
	if r.Errors > 0 {
		os.Exit(1)
	}
}
