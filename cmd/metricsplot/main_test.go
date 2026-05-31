package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestReadSamplesClampsNegativeProcessCPU(t *testing.T) {
	path := filepath.Join(t.TempDir(), "metrics.csv")
	data := "timestamp,cpu_pct,mem_used_bytes,mem_available_bytes,load1,load5,load15,bench_rss_bytes,proxy_rss_bytes,conn_established,app_cpu_pct,proxy_cpu_pct,loadgen_cpu_pct,loadgen_rss_bytes\n" +
		"2026-05-31T20:52:18Z,90.47,2775470080,5556514816,4.81,2.92,1.56,345190400,2108542976,0,9.40,41.30,-332.02,0\n"
	if err := os.WriteFile(path, []byte(data), 0o644); err != nil {
		t.Fatalf("write metrics: %v", err)
	}

	samples, err := readSamples(path)
	if err != nil {
		t.Fatalf("readSamples: %v", err)
	}
	if len(samples) != 1 {
		t.Fatalf("samples = %d, want 1", len(samples))
	}
	if samples[0].loadCPUPct != 0 {
		t.Fatalf("loadCPUPct = %v, want 0", samples[0].loadCPUPct)
	}
}
