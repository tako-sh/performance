# Production buffer release — 26 October 2026

Releasing unused buffers while preserving 64 KiB transfer reads reduces process
PSS from **2,273.68 to 1,019.02 MiB (55.2%)** with 20,000 exercised TLS connections
held open, and from **577.97 to 335.30 MiB (42.0%)** with 2,000 uploads followed
by streaming responses. Both are below Caddy in these workloads.

The candidate is [merged into Tako master](https://github.com/tako-sh/tako/commit/1a90cfd31ee3ca3a30c6feaf74acf302788726ba).
Extended paired tests and matched-rate checks did not identify a repeatable
processing-cost regression. Saturated results remain noisy, including a lower
mean for chunked uploads; the observations and uncertainty are retained below.
This is not a claim of exactly zero overhead or a universal lead over Caddy.

## Implementation and identity

The candidate uses a pinned local `pingora-core 0.9.0` dependency. Empty read
buffers return to a bounded pool when the underlying read would block, reaches
EOF or fails; unread bytes stay with their connection. The pool holds at most
eight 64 KiB buffers per polling thread (512 KiB), independent of connection
count. Transfers retain 64 KiB reads and Tokio's write buffering. Completed
HTTP/1 body-reader allocations are released after final chunks and retry data
have been copied; pipelined read-ahead remains separately owned.

There are no benchmark switches or per-read variant dispatch in the candidate.
Zero-capacity upstream/PROXY sockets remain unbuffered. TLS offloading stays
disabled: the [separate experiment](../20261026-tls-offload/README.md) found a
handshake-throughput cost. Flow-control windows and connection reuse are unchanged.
The dependency provenance, license and removal criteria live in
[Tako's vendor documentation](https://github.com/tako-sh/tako/blob/35c4234595be4e66fc86339c2a37a298653a4c63/vendor/README.md).

- Unchanged baseline: `738e023e721cb6bfe63cda184b8e78ad7bf8d1c6`.
- Production candidate: `35c4234595be4e66fc86339c2a37a298653a4c63`.
- Primary performance head: `63b4b55153ca071491b531b78cf9900900462490`;
  measured PR merge checkout: `271c306e841c813cf3c18d732d0cb3a175d4f79a`.
- Rust 1.99.1, Go 1.26.3, Caddy 2.11.7 with rate-limit plugin 0.1.0.
- [Primary run](https://github.com/tako-sh/performance/actions/runs/40340201528),
  [HTTP/2 follow-up](https://github.com/tako-sh/performance/actions/runs/40345677779),
  [chunked-upload follow-up](https://github.com/tako-sh/performance/actions/runs/40346965514).

Both binaries were built from the same checkout path with locked dependencies.
Follow-ups downloaded those exact binaries and checked their hashes before
running. Every group's `build.txt` and `metadata.json` record their identities;
`validation.json` records the longer-duration override and wrapper hash.
[Provenance](provenance.json) records workflow heads, measured checkouts and artifacts.

## Setup and correctness

Free standard Ubuntu GitHub runners run the full Tako server, original Linux
installer/provisioning and a real deployed Go app. Each comparison container
has a shared **2 CPU quota, 8 GiB RAM and no swap**. Client, proxy and app compete
for that quota. It is not an exclusive two-core VM. Groups use separate hosts;
compare variants within each group, never pool absolute RPS across groups.

All **188 cases** passed: 18 memory, 54 short HTTP/1, 36 short HTTP/2 and 80
longer traffic cases. All payload/protocol/status checks passed with zero client
errors. Every held case kept exactly 20,000 unique established sockets and
returned all 420,000 expected responses. No cases or repetitions are excluded.

Each case starts fresh processes. Variant order reverses on alternate repeats.
Traffic has three seconds of warmup, then either 15 seconds of measurement in
the three-proxy matrix or 60 seconds in the eight-pair follow-ups. RPS uses actual
completion time. CPU spans the acknowledged measurement start through request
drain. Fixed-rate latency includes queueing from the scheduled arrival.

The candidate also passed full Tako CI, Linux CLI and E2E tests, 513 affected
Pingora protocol tests (one ignored), 11 listener tests, 175 Tako proxy tests and
eight local full-server smoke cases. The unrelated external-network connector
suite is not claimed.

## Live retained memory

These are means of each run's median holding-phase process PSS. Kernel socket
memory, client memory and app-process memory are excluded. Each held connection
completes 21 checked requests. Streaming cases upload 128 KiB, wait for every
flushed response prefix, hold ten seconds, then verify every released suffix.
These are retained-memory measurements, not maximum-throughput tests.

| Workload | Baseline MiB | Candidate MiB | Caddy MiB | Saving vs baseline |
| --- | ---: | ---: | ---: | ---: |
| 20,000 held TLS connections | 2,273.68 | 1,019.02 | 1,054.17 | 55.2% |
| 2,000 uploads then streaming responses | 577.97 | 335.30 | 486.44 | 42.0% |

Candidate PSS is 3.3% below Caddy for held connections and 31.1% below it for
streaming responses. Reclamation depends on polling an empty reader; it cannot
free unread data or a buffer whose owner has stopped polling altogether.

## Throughput, latency and CPU

[Complete tables](details.md) include every group, Caddy control, PSS, p95/p99
and CPU/request. [Longer paired tables](paired-details.md) show every repetition.
[Derived values](analysis.json) include each paired percentage change.

The longer small-response check averaged **6,032.20 → 6,024.16 RPS (−0.13%)**,
with CPU/request **+0.09%**, effectively unchanged p95, and p99 **−0.08%**.
Five of eight pairs were faster. The approximate paired 95% t-interval for RPS
change spans −1.28% to +1.02%; this is no evidence of a repeatable slowdown, not
proof of exactly zero overhead.

Longer chunked uploads averaged **912.31 → 900.81 RPS (−1.26%)**, with
CPU/request **+1.71%**. Four pairs were faster and four slower; the approximate
paired RPS interval spans −4.69% to +2.28%. This remains an uncertain saturation
result rather than proof of exact throughput parity.

The [matched-rate upload check](https://github.com/tako-sh/performance/actions/runs/40352155109)
then offered 250 uploads/s to leave headroom on slower runners. Every case
completed all 15,000 uploads with zero errors. CPU/request was **3,130.83 →
3,134.00 µs (+0.10%)**, p95 **3.875 → 3.885 ms**, and p99 **4.079 → 4.102 ms**
(+0.024 ms). Four CPU pairs were higher and four lower; the approximate paired
CPU interval spans −1.37% to +1.61%. These checks did not find a consistent
processing-cost increase. A matched-rate check alone does not establish peak
throughput parity; it is reported alongside the mixed saturation results.

HTTP/2 downloads averaged **552.28 → 563.02 RPS (+1.94%)** in the longer check,
with CPU/request +0.49%. Individual pairs ranged from −2.74% to +18.63%, and
tail latency varied substantially in both the original and longer groups.
The approximate paired RPS interval spans −3.60% to +8.11%; do not claim a
reliable download speedup from this mean. At a matched 1,000 HTTP/2 requests/s,
CPU/request changed by −0.04%, p95 by +0.08% and p99 by +0.08% (1.411 → 1.412 ms).
The earlier slight fixed-rate CPU increase did not persist.

The unfavorable short results remain in this report. Chunked uploads were
2.97% lower with 3.46% higher CPU/request in three short repeats, all with lower
RPS. Short HTTP/2 downloads averaged 2.23% lower with variable tail latency.
Those observations triggered the longer checks using identical binaries; no
code was changed between these runs. The longer groups use new hosts and are
reported separately, without replacing or averaging away the original results.

A local exploratory increase to 64 spare buffers per thread did not show a
consistent benefit and was not selected. All official runs above use eight.
This report supports conclusions about the measured scenarios and hardware
limits, not exact parity on every workload or machine.

### Caddy comparison

The candidate remains faster than Caddy for small responses, connection churn
and HTTP/2 downloads in the matched three-proxy group. Existing bulk-transfer
gaps remain: Caddy is faster for HTTP/1 uploads, chunked uploads and downloads,
and HTTP/2 uploads. These gaps also exist in unchanged Tako. In particular:

- HTTP/1 small: baseline 15,544, candidate 15,605, Caddy 12,616 RPS.
- HTTP/2 small: baseline 14,616, candidate 14,728, Caddy 9,450 RPS.
- HTTP/1 download: baseline 1,035, candidate 1,053, Caddy 1,190 RPS.
- HTTP/2 upload: baseline 253, candidate 254, Caddy 563 RPS.

Do not generalize the small-response advantage to all transfers. The historical
five-proxy VM charts in the root report use different hardware, concurrency and
builds; these held-memory values do not replace active-saturation memory rows.

## Canceled setup run

[Run 40351726360](https://github.com/tako-sh/performance/actions/runs/40351726360)
started with a 500-upload/s target. Before inspecting its measurements, the
configuration was changed to 250/s to leave more headroom on slower runner CPUs.
That push canceled the first run. Its [partial artifact](canceled-500-rate/) is
retained for provenance, excluded from the 188 completed cases and not used to
judge performance. The 250/s workload is separate from the saturation tests.

## Reproduce and inspect

Use the [production validation workflow](../../.github/workflows/buffer-release.yml)
and [guide](../../diagnostics/release-validation/README.md). Source pins reproduce
this experiment rather than tracking future master. The follow-up workflows
reuse the original binary artifact; after its seven-day retention expires,
rebuild the pinned sources and update their source run ID. Results are retained
here beyond the Actions artifact lifetime.

- [Memory](ci-memory/), [HTTP/1](ci-h1/), [HTTP/2](ci-h2/).
- [Longer small responses](ci-small-repeat/), [longer HTTP/2 downloads](ci-h2-download-repeat/),
  [matched-rate HTTP/2](ci-h2-rate-repeat/), [longer chunked uploads](ci-chunked-repeat/),
  [matched-rate chunked uploads](ci-chunked-rate-repeat/).
- Run `python3 analyze.py .` to verify counts, correctness, socket counts,
  limits and common binary identities, then regenerate `analysis.json`.
- Run `python3 render-details.py .` to regenerate both detail tables.

Raw runtime logs and native profiling stacks remain private. Only sanitized
measurement JSON and build identities are published.
