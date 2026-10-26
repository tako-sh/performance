# Buffer lifetime investigation — 26 October 2026

This is the historical prototype investigation. The subsequent
[production validation](../20261026-buffer-release/README.md) records the merged
implementation and longer follow-ups. Original findings below are retained.

Releasing unused buffers delivers a substantial memory saving while retaining
64 KiB socket reads. The combined prototype reduced process PSS from **2,270 to
1,016 MiB (55.2%)** with 20,000 exercised TLS connections held open, and from
**569 to 329 MiB (42.1%)** with 2,000 completed uploads followed by open streaming
responses. Both figures are below Caddy in these workloads.

**The performance acceptance requirement has not passed.** The combined
candidate's HTTP/1 small-response mean was 0.9% lower, with 0.6% higher CPU per
request; three short repeats do not establish whether that difference is noise.
The broader tests also revealed existing Caddy advantages in bulk HTTP/1
transfers and HTTP/2 uploads. Production defaults and public release tables
remain unchanged.

## Candidates and setup

The [experiment guide](../../diagnostics/buffer-lifetime/README.md) documents the
implementation and commands. All five variants run in the full server with a
real deployed Go app and original Linux provisioning:

- **baseline:** unchanged Tako source and Pingora, built as a separate binary.
- **idle:** recycle an empty accepted-socket buffer when its read would block;
  retain 64 KiB batching and unread bytes. Use at most eight spare buffers per
  polling thread. This is automatic lifetime management, not a smaller read size.
- **body:** release the HTTP/1 body-reader allocation after the final copied
  chunk, preserving retries and pipelined overread, before the response finishes.
- **combined:** both changes.
- **Caddy:** pinned Caddy 2.11.7 with the existing rate-limit plugin.

The [Actions run](https://github.com/tako-sh/performance/actions/runs/40295285301)
used free standard Ubuntu runners. Each comparison job imposed a shared 2 CPU
quota, 8 GiB RAM and no swap; the load generator and app share that quota with
the proxy. Each case uses fresh processes; each workload has three repetitions,
reversing variant order on the second. HTTP/1, HTTP/2 and memory groups ran on
separate hosts. Compare variants within a group, not absolute values across jobs.

Source identity: Tako `f0ed5d938a4f26f4c775336c8f16aa572fe20dae`, Pingora 0.9.0,
upstream test fixtures `702f69015e53f7244d6ad2e743de571d859a70a4`, performance head
`d437b0383fedfeb91c304a39815e11f6427ed5cf`, measured PR merge checkout
`934fb17570c306f9139cf5bd7c2c05948b572957`, Rust 1.99.1, Go 1.26.3. Per-group
`build.txt` and `metadata.json` record binary hashes and limits. The original
build manifest accidentally hashed itself while being written; ignore only its
`build/build.txt` hash row. Binary hashes are unaffected, and metadata contains
the final manifest hash. The workflow now lists binaries explicitly.

## Live retained memory

These are means of each run's median holding-phase process PSS. Kernel socket
memory, load-generator memory and app-process memory are excluded. Held cases
exercise every connection with 21 checked responses; stream cases upload 128 KiB
each, wait for all flushed response prefixes, hold ten seconds, then verify the
released response suffixes.

| Variant | Held PSS MiB | Valid held cases | Streaming PSS MiB | Valid stream cases |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 2,269.86 | 3/3 | 568.69 | 3/3 |
| Idle | 1,015.69 | 2/3 | 445.16 | 3/3 |
| Body | 2,266.81 | 3/3 | 454.32 | 3/3 |
| Combined | 1,015.79 | 3/3 | 329.38 | 3/3 |
| Caddy | 1,049.98 | 3/3 | 473.48 | 3/3 |

The idle held mean above uses the two valid runs; the excluded run and failure
remain in the raw data. Combined held values range from 1,014.08 to 1,018.77 MiB;
baseline values range from 2,266.48 to 2,274.35 MiB. Combined uses 3.3% less than
Caddy here. Streaming combined uses 30.4% less than Caddy. Body release alone
saves 20.1% on the streaming workload and has no material effect on bodyless held
connections, as expected.

The streaming savings show that idle L4 reclamation and completed-body release
address separate retained allocations. The implementation still retains unread
bytes and cannot reclaim a buffer if its owner stops polling reads entirely.

## Throughput, latency and CPU

All **90 HTTP/1 and 60 HTTP/2 cases passed**, checking status, full payload and
negotiated protocol. Traffic has three seconds of warmup and fifteen seconds of
nominal measurement. CPU spans the acknowledged measurement start through drain;
RPS uses actual completion time. Fixed-rate latency includes queueing from the
scheduled arrival.

The [combined comparison table](combined-throughput.md) contains unchanged Tako,
combined and Caddy side by side. Complete per-variant tables are in
[HTTP/1 details](h1-details.md) and [HTTP/2 details](h2-details.md).

Against unchanged Tako, combined mean throughput changed by:

- HTTP/1 small: **−0.89%**, CPU/request **+0.62%**. Paired RPS changes were
  −1.91%, +0.31%, −1.10%; these are not proof of no regression.
- HTTP/1 upload/chunked upload/download: **+3.41% / +3.94% / +2.84%**, with
  lower mean CPU per request. Individual pairs vary; these are diagnostics.
- New TLS connection per request: **+1.75%**, CPU/request **−1.50%**.
- HTTP/2 small/upload/download: **+1.16% / +0.68% / +0.60%**, with lower mean
  CPU per request. HTTP/2 fixed-rate CPU/request was **1.22% higher**.

At 1,000 requests/s, mean p99 was 1.35→1.36 ms for HTTP/1 and 1.51→1.53 ms for
HTTP/2. Those small differences need longer paired checks before any default
change. Saturated p99 values are reported separately in raw results and should
not substitute for matched-load latency comparisons.

The body-only candidate deserves particular scrutiny: its HTTP/1 small-response
RPS was lower in all three pairs (−4.63%, −0.79%, −3.27%), with higher CPU in all
three. Its HTTP/2 download mean was also lower. The body switch shares the
experimental wrapper binary with idle support, even when disabled, so those
changes cannot be attributed solely to the body-release statement without a
separate compiled control. The combined prototype is the stronger candidate,
but it has not cleared the strict no-regression bar either.

### Caddy comparison limits

Combined remained faster than Caddy for small responses, TLS churn and HTTP/2
downloads. It was slower for HTTP/1 uploads, chunked uploads and downloads, and
HTTP/2 uploads. These gaps also exist in the unchanged baseline:

- HTTP/1 download: baseline 593, combined 610, Caddy 881 requests/s.
- HTTP/1 upload: baseline 628, combined 649, Caddy 761 requests/s.
- HTTP/2 upload: baseline 146, combined 147, Caddy 382 requests/s.

Thus the earlier small-response advantage must not be generalized to every
transfer workload. Source inspection suggests HTTP/2 receive-window settings
as one lead: Pingora's downstream builder keeps default flow-control windows,
whereas Go's server configures larger ones. This is not a confirmed cause; a
controlled test must account for the extra buffered-data allowance. No window
change is included in this prototype.

## Socket-counter correction

The memory job is **failed**, not fully green: `r3-idle-held` returned all 420,000
correct responses but sampled 20,001 established rows once, then 20,000. The same
pattern occurred in a separate legacy fixed-size run. The artifacts did not
capture socket identities, so the original case remains invalid.

A controlled local reproduction held exactly 20,000 sockets while churning an
unrelated listener. Across 100 scans, `/proc/net/tcp` returned 20,001–20,020 rows,
but exactly 20,000 unique socket inodes every time. The proc table walk is not
atomic and can repeat rows. The shared counter now deduplicates by endpoints
plus inode; it still rejects a real surplus or missing socket. Regression tests
cover duplicates, distinct sockets, IPv6, closing sockets and inode-zero entries.

A fresh [local full-server check](count-fixed-local/summary.json) with the fixed
counter passed unchanged baseline, idle and combined at 20,000 connections, all
420,000 responses correct per case. PSS was approximately 2,204, 1,002 and 1,004
MiB respectively. This is a separate host and one repeat; it validates the fix
and is not pooled into the Actions memory table. The local control uses the
earlier diagnostic size-switch binary fixed at 64 KiB; the Actions control is
the fully unchanged binary. All three original combined held cases passed even
before the counter correction.

## Correctness and retained evidence

The build passed nine isolated-reader tests, 505 affected Pingora protocol tests
(one ignored), eleven listener tests, 161 Tako proxy tests and the Go fixture/
client tests. Tests cover 64 KiB batching, partial/unread data, idle reactivation,
wakers, zero reads, EOF/errors, queued writes, bounded pooling, body completion,
and Content-Length/chunked pipelining. The full unrelated upstream connector
suite is not claimed: it requires direct external connections unavailable in the
local environment.

- [Memory raw data](ci-memory/), [HTTP/1 raw data](ci-h1/), [HTTP/2 raw data](ci-h2/).
- [Original memory summary, including invalid case](memory-details.md).
- [Counter-corrected local check](count-fixed-local/).
- [Independent TLS offload experiment](https://github.com/tako-sh/performance/pull/3).

The next acceptance work is a focused longer small-response comparison with
compiled variants that isolate dispatch overhead, plus investigation of the
existing Caddy bulk-transfer gaps. A memory improvement alone does not authorize
a production default change under the stated requirement.
