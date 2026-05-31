package main

import (
	"context"
	"errors"
	"net"
	"sync"
	"testing"
)

type timeoutError struct{}

func (timeoutError) Error() string   { return "temporary timeout" }
func (timeoutError) Timeout() bool   { return true }
func (timeoutError) Temporary() bool { return true }

func TestClassifyErrorDetectsTimeouts(t *testing.T) {
	cases := []error{
		context.DeadlineExceeded,
		timeoutError{},
		errors.New("Get \"https://bench.test\": context deadline exceeded (Client.Timeout exceeded while awaiting headers)"),
		errors.New("dial tcp 127.0.0.1:18443: i/o timeout"),
	}

	for _, err := range cases {
		if got := classifyError(err); got != "timeout" {
			t.Fatalf("classifyError(%q) = %q, want timeout", err.Error(), got)
		}
	}
}

func TestClassifyErrorDetectsLocalAddressExhaustion(t *testing.T) {
	cases := []error{
		&net.OpError{Op: "dial", Err: errors.New("bind: address already in use")},
		errors.New("dial tcp 127.0.0.2:0->127.0.0.1:18443: connect: cannot assign requested address"),
	}

	for _, err := range cases {
		if got := classifyError(err); got != "local_address_exhausted" {
			t.Fatalf("classifyError(%q) = %q, want local_address_exhausted", err.Error(), got)
		}
	}
}

func TestClassifyErrorDetectsFileDescriptorExhaustion(t *testing.T) {
	err := errors.New("dial tcp 127.0.0.6:0->127.0.0.1:18443: socket: too many open files")

	if got := classifyError(err); got != "too_many_open_files" {
		t.Fatalf("classifyError(%q) = %q, want too_many_open_files", err.Error(), got)
	}
}

func TestRecordErrorKeepsOnlySampledMessages(t *testing.T) {
	counts := map[string]int64{}
	samples := map[string][]string{}
	var mu sync.Mutex

	for i := 0; i < 5; i++ {
		recordError(&mu, counts, samples, "timeout", errors.New("context deadline exceeded"))
	}

	if counts["timeout"] != 5 {
		t.Fatalf("count = %d, want 5", counts["timeout"])
	}
	if got := len(samples["timeout"]); got != 3 {
		t.Fatalf("samples = %d, want 3", got)
	}
}
