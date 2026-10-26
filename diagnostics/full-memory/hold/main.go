// Hold a known number of exercised TLS connections without saturating the app.
package main

import (
	"bufio"
	"crypto/tls"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"sync"
	"time"
)

func main() {
	n := flag.Int("concurrency", 20000, "connections to hold")
	phaseFile := flag.String("phase-file", "", "phase marker for the memory sampler")
	flag.Parse()
	if *n < 1 || *phaseFile == "" {
		panic("positive concurrency and phase-file are required")
	}
	started := time.Now()
	connections := make([]*tls.Conn, *n)
	readers := make([]*bufio.Reader, *n)
	phase := func(value string) {
		data, _ := json.Marshal(map[string]string{"phase": value})
		if err := os.WriteFile(*phaseFile+".tmp", data, 0644); err != nil {
			panic(err)
		}
		if err := os.Rename(*phaseFile+".tmp", *phaseFile); err != nil {
			panic(err)
		}
	}
	request := func(i int) error {
		if err := connections[i].SetDeadline(time.Now().Add(120 * time.Second)); err != nil {
			return err
		}
		if _, err := io.WriteString(connections[i], "GET /plaintext HTTP/1.1\r\nHost: bench.test\r\n\r\n"); err != nil {
			return err
		}
		response, err := http.ReadResponse(readers[i], nil)
		if err != nil {
			return err
		}
		body, err := io.ReadAll(response.Body)
		response.Body.Close()
		if err != nil {
			return err
		}
		if response.StatusCode != 200 || string(body) != "hello, world\n" {
			return fmt.Errorf("unexpected status/body: %d %q", response.StatusCode, body)
		}
		return nil
	}
	batch := func(work func(int) error) {
		gate := make(chan struct{}, 64)
		failures := make(chan error, *n)
		var wg sync.WaitGroup
		for i := range *n {
			wg.Add(1)
			go func(i int) {
				defer wg.Done()
				gate <- struct{}{}
				defer func() { <-gate }()
				if err := work(i); err != nil {
					failures <- err
				}
			}(i)
		}
		wg.Wait()
		close(failures)
		if err, failed := <-failures; failed {
			panic(err)
		}
	}
	phase("connecting")
	batch(func(i int) error {
		dialer := &net.Dialer{Timeout: 120 * time.Second, LocalAddr: &net.TCPAddr{IP: net.ParseIP(fmt.Sprintf("127.0.0.%d", 2+i%16))}}
		connection, err := tls.DialWithDialer(dialer, "tcp", "127.0.0.1:18443", &tls.Config{InsecureSkipVerify: true, ServerName: "bench.test", NextProtos: []string{"http/1.1"}})
		if err != nil {
			return err
		}
		connections[i], readers[i] = connection, bufio.NewReader(connection)
		return request(i)
	})
	phase("exercising")
	batch(func(i int) error {
		for range 20 {
			if err := request(i); err != nil {
				return err
			}
		}
		return nil
	})
	phase("holding")
	time.Sleep(10 * time.Second)
	phase("closing")
	for _, connection := range connections {
		connection.Close()
	}
	phase("closed")
	time.Sleep(3 * time.Second)
	json.NewEncoder(os.Stdout).Encode(map[string]any{
		"concurrency": *n, "requests": *n * 21, "bytes": *n * 21 * 13,
		"errors": 0, "status_counts": map[string]int{"200": *n * 21},
		"duration_sec": time.Since(started).Seconds(), "requests_per_sec": 0,
		"note": "Connection-retention experiment; RPS is intentionally not measured.",
	})
}
