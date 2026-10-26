# Complete public benchmark

Run `.github/workflows/full-suite.yml` in **tako-sh/performance**. This refreshes
the entire public comparison, using the same workload as the original VM page:

- Tako, nginx, HAProxy, Envoy, and Caddy at 1,000, 2,500, 5,000, 7,500,
  10,000, 15,000, and 20,000 concurrent HTTP/1.1 TLS clients.
- Tako channel publish and workflow enqueue at 500, 1,000, 2,000, 4,000,
  and 8,000 concurrent clients.
- 10-second warmup, 30-second measurement, 60-second request timeout,
  16 loopback source addresses, and a 10-second cooldown between fresh processes.
- Three repetitions: **105 proxy cases and 30 feature cases**. A separate
  seven-case smoke run validates startup, TLS, payloads, and feature operations.

Every case measures throughput, p50/p95/p99, HTTP status counts, client errors,
process PSS/RSS/private memory, and CPU. nginx includes its master and workers;
Tako's app and workflow processes are counted separately from the proxy.
Memory is sampled during the same run as throughput, never substituted from a
different held-connection experiment. Expected overload responses/timeouts are
retained as results; setup failures and invalid counts fail the workflow.

The proxy, load generator, app, and sampler share two assigned logical CPUs,
a 2-CPU quota, 8 GiB RAM, and no swap in a disposable container. The outer host
is a free standard GitHub runner. Record its CPU model, kernel, affinity, quota,
package versions, image identity, and all binary hashes with the results.
This is a new hardware baseline, not an isolated measurement of the buffer patch
against the previous exe.dev VM.

All jobs use one built runtime image and the same binaries. The Tako server and
JavaScript SDK come from the same immutable source revision. Envoy and Ubuntu
images are pinned by digest; Caddy and its rate-limit plugin are locked in Go
modules. nginx/HAProxy packages are installed once in the shared runtime image;
record their exact versions and binary hashes. The original proxy configurations
remain in `configs/`, with worker count fixed to two and a fresh upstream port
per case to prevent previous cases' TIME_WAIT sockets consuming its port budget.

Each HTTP repetition runs all five proxies and all seven concurrency levels on
one host; ordering rotates across repetitions and reverses at alternate levels.
Feature repetitions run separately. Preserve every raw repetition; report the
mean and spread rather than selecting the best run. Different hosts may differ
in speed, so compare proxies within each matched repetition as well.

The original `cmd/loadgen` workload is preserved. Two accounting corrections
record subsecond start timestamps and count truncated response bodies only as
client errors, rather than also counting their HTTP status as a completed
response. A regression test covers truncated responses. RPS uses actual elapsed
time including drain. Latency ends when response headers arrive; response bytes
are then drained before another request. Resource samples are filtered by the
load generator's measurement timestamps. CPU percentages use
the shared two-CPU budget as 100%. PSS excludes kernel socket memory.

Build artifacts live seven days, measurements fourteen days. Commit sanitized
JSON, metadata, build identities, derived data, and reports before expiry. Do not
publish runtime logs, credentials, private host identities, or certificate keys.
Replace the whole website dataset and its conclusions from a completed suite;
keep older results in the repository archive rather than mixing them into the
current benchmark page.
