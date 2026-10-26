# Buffer lifetime experiments

Measure two independent Pingora 0.9 changes in the full Tako server, with the
same pinned baseline as the earlier fixed-buffer investigation. Production Tako
is unchanged. The [workflow](../../.github/workflows/buffers.yml) lives in this
performance repository and uses free standard GitHub runners.

See the [measured results](../../results/20261026-buffer-lifetime/README.md) for
memory savings, the incomplete performance acceptance and retained failures.

## Candidates

- **baseline:** unchanged Tako source and Pingora dependency, built before the
  patch. Its accepted-socket read buffer stays at 64 KiB.
- **idle:** replace only the ordinary listener's read buffering. Preserve 64 KiB
  socket reads while data flows; when an empty buffer's read returns Pending,
  return the allocation to a bounded pool. Keep unread bytes until consumed.
- **body:** after a complete HTTP/1 request body has been copied to returned
  chunks and retry storage, drop its reader buffer before the response ends.
  Preserve pipelined overread separately. Upstream body allocation is unchanged.
- **combined:** enable both changes.
- **caddy:** pinned Caddy with the same rate-limit plugin as the existing harness.

One candidate binary contains both switches (`TAKO_BENCH_IDLE_L4` and
`TAKO_BENCH_RELEASE_BODY`). The unchanged baseline is a separate binary; do not
claim an enum-dispatched control inside the patched binary is untouched Tako.
The temporary switches are diagnostic tools, not proposed user configuration.
`prepare.py` applies checked substitutions to the published `pingora-core 0.9.0`
source and copies the tested reader implementation into it.

The reader uses safe Rust and Tokio's unchanged `BufWriter`. Each polling thread
retains at most eight spare 64 KiB read buffers (512 KiB), independently of
connection count. Pooling avoids allocating on every wakeup; no global pool lock
or per-connection idle timer is added. Buffers with unread data stay owned by the
connection. Other sizes are dropped rather than pooled. Allocations returned to
the allocator do not necessarily leave RSS immediately, so measure PSS too.

This releases buffers at a read that would block, rather than waiting an idle
interval. That can also happen between records during an active transfer; the
CPU and transfer tests must catch any extra pool/allocator cost. It does not
release a buffer when the application has stopped polling reads entirely.
The custom PROXY-protocol listener and upstream L4 sockets are unchanged.

## Tests and workload

The workflow tests the isolated reader, the affected Pingora protocol/listener
suites with both switches enabled, Tako's proxy suite, and the Go fixtures/client.
The published crate omits TLS fixtures, so copy them from the exact upstream
revision. Unrelated connector tests that dial public IPs are not part of the
selected suite; they cannot run in environments without direct TCP egress.
`pingora-tests.lock` pins the separate upstream test dependencies, including the
Tokio version compatible with Pingora 0.9.

Reader tests cover partial reads, read-ahead, idle/reactivation, real waker
resumption, zero-length reads, EOF/errors, unbuffered operation, bounded pooling,
64 KiB batching, and preserved queued writes/flushes. Body tests cover completed
large uploads and chunked/Content-Length pipelining before response completion.

Three Actions jobs run paired comparisons under a shared **2 CPU quota, 8 GiB,
no-swap** container limit, with all variants using the same app and certificate.
Each group runs all five variants three times, reversing order on alternate
repetitions. Each case starts fresh proxy/app processes.

| Group | Workloads |
| --- | --- |
| memory | 20,000 exercised TLS connections held open; 2,000 completed 128 KiB uploads followed by responses held streaming |
| h1 | Small responses, matched 1,000 requests/s, 1 MiB uploads, chunked uploads, downloads, and new TLS connections per request |
| h2 | Small responses, matched 1,000 requests/s, 1 MiB uploads and downloads |

Traffic runs warm up for three seconds and measure for fifteen seconds. The
client verifies the negotiated HTTP version, status, and response content;
upload handlers validate the complete input. The fixed-rate client measures
latency from scheduled arrival, including queue delay, and drains scheduled work
instead of quietly discarding it. Overload can extend the run beyond its nominal
duration. Check that the offered rate is below capacity for every compared proxy.

The streaming test uploads first and waits for every response's flushed `ready`
prefix before marking a ten-second holding phase. A control request releases
responses, and the client checks every `done` suffix. This measures live unused
body-buffer retention, not post-close allocator cleanup. The held-connection
mode reuses the existing 21-requests-per-connection client and validates the
established socket count.

PSS/RSS/private memory are sampled every 250 ms for the proxy process. CPU for
ordinary traffic starts when the sampler acknowledges the client's post-warmup
barrier and ends after request drain. Per-phase client CPU samples help identify
load-generator bottlenecks. TLS handshake counts and wall duration come from
client tracing; these are not a CPU profile or proof of server-worker contention.
Do not turn on TLS offloading solely because connection churn is expensive.

## Running and artifacts

Use the PR-triggered workflow until `buffers.yml` exists on the default branch.
Afterward it can be dispatched with `gh workflow run buffers.yml -R
tako-sh/performance --ref <branch>`. Follow Tako's `commands/performance.md` for
run selection, artifact download, publication requirements, and privacy checks.

Build produces `buffer-binaries` (seven-day retention). Comparison jobs upload
`buffer-results-<group>-<sha>` (fourteen days): raw JSON and `build.txt`, excluding
runtime logs and machine-specific source paths. Inspect job status and every
case's success flag; partial artifacts are not a successful suite.

```bash
python3 diagnostics/buffer-lifetime/summarize.py <downloaded-results-directory>
```

Local Linux validation can reuse the existing Docker image and original installer.
Mount the pinned source at `/source`, this repository at `/perf`, the binaries
at `/build`, and a fresh output directory at `/results`. Set the entrypoint to
`bash /perf/diagnostics/buffer-lifetime/entrypoint.sh`. Preserve the existing
private cgroup/network namespaces, privilege, CPU/memory limits, and native
library setup. Add `--smoke --repetitions 1` for a short correctness check.
Use `--scenarios` and `--variants` for focused reruns; always include the matching
unchanged control. The workflow is the authoritative build command reference.

## Acceptance

Lower memory alone is insufficient. Require no repeatable loss versus unchanged
Tako in successful throughput, matched-load p95/p99, and CPU per request/byte,
and keep Tako faster than Caddy on the compared workload. A small or inconclusive
difference needs more paired measurements; three short repetitions do not prove
no regression. Keep public release tables and production defaults unchanged
until the relevant coverage passes. Profile handshake contention before adding
TLS offloading as another candidate; its extra runtime threads can cost memory.
