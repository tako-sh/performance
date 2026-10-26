# TLS offload investigation — 26 October 2026

One offload thread substantially reduced established-request tail latency under
heavy new-connection traffic, but reduced completed handshake throughput by
about **2–3%**. Two threads gave a smaller latency benefit and increased CPU per
request by about **7%**. Neither setting clears the stated no-throughput-loss
requirement. Production TLS offloading remains disabled.

Both nonzero offered handshake rates exceeded this runner's capacity. These
results describe overload scheduling, not a sustainable-load latency win or a
recommended default. The experiment is independent of the buffer-lifetime
prototype; no buffer patch is applied here.

## Why this experiment was run

A local server-only CPU profile first established a reason to test offloading.
With foreground arrivals fixed at 1,000 requests/s, adding a separate client
opening TLS connections raised p99 from 1.42 ms to 47.21 ms. All requests were
correct. The background completed about 2,337 requests/s on that local host.

Of 2,105 sampled server CPU stacks in the competing-traffic case, 21.38% included
OpenSSL `EVP_DigestSignFinal` and 18.38% included
`BN_mod_exp_mont_consttime_x2`. These inclusive percentages overlap. Symbol
resolution was incomplete, and the profile included setup/warmup. Shared CPU
quota also contributes to latency; the observation does not isolate every source
of interference.

The [reviewed profile aggregates and request data](local-profile/) preserve that
evidence. Raw perf stacks and decoded reports remain private because they can
contain machine paths and addresses. The legacy profile summary's CPU-per-success
field includes competing background CPU divided by foreground requests; it must
not be used as a per-request efficiency measure. Acceptance measurements below
omit profiling and use both streams in their CPU denominator.
The local profile used the earlier diagnostic size-switch control fixed at
64 KiB, without offloading or buffer-lifetime changes. The Actions control below
is a separate build of the fully unchanged pinned source.

## Controlled Actions results

The [Actions run](https://github.com/tako-sh/performance/actions/runs/40298045692)
passed **all 48 cases**, with no response, payload, protocol or transport errors.
Each background request completed a fresh TLS handshake. There are four repeats
of unchanged Tako, one offload thread, two offload threads and pinned Caddy at
each background arrival rate. Variant order reverses on alternating repeats.

The foreground offers 1,000 requests/s using established TLS connections. The
background offers 0, 1,500 or 2,500 new TLS connections/s. Both clients start from
a sampler-acknowledged barrier after foreground warmup. They schedule fifteen
seconds of arrivals, count latency from scheduled arrival and drain all requests.
Queues are not silently dropped. The RSA-2048 certificate is shared, and TLS
session caching is disabled in the client.

| Offered new TLS/s | Variant | Foreground p99 ms | Completed new TLS/s | Server CPU µs/total request |
| ---: | --- | ---: | ---: | ---: |
| 1,500 | Baseline | 145.07 | 694.91 | 1,078.93 |
| 1,500 | One offload thread | 33.82 | 675.66 | 1,073.00 |
| 1,500 | Two offload threads | 69.21 | 669.01 | 1,156.53 |
| 1,500 | Caddy | 192.60 | 623.53 | 1,306.33 |
| 2,500 | Baseline | 128.66 | 729.79 | 1,235.62 |
| 2,500 | One offload thread | 33.84 | 715.71 | 1,223.86 |
| 2,500 | Two offload threads | 67.79 | 702.85 | 1,327.62 |
| 2,500 | Caddy | 184.35 | 662.10 | 1,478.43 |

Numbers are means across four repetitions. See [all metrics](ci-details.md) for
foreground completion rates, p95, PSS and thread counts, and [raw cases](ci/) for
per-repeat variability, CPU/memory samples, arrival counts and drain durations.

One thread reduced foreground p99 by approximately 74–77%, while background
completion rate fell 2.77% at 1,500 offered arrivals/s and 1.93% at 2,500. Total
completed work is identical, so longer drain time is a real trade-off, not a
reduction in requested work. Its CPU per total request was slightly lower on
average; the experiment does not establish absence of an efficiency regression
under other loads. Two threads reduced background throughput about 3.7% and
increased CPU per total request 7.2–7.5%.

All offered background rates here are far above their completed rates. Requests
continue after the foreground's nominal measurement interval, so average
background throughput includes a changing foreground/background mix during
drain. These values are not independent sustained handshake capacity estimates.
The next useful latency comparison would use background rates below the
baseline's observed capacity on the same runner. That has not been measured in
this run; a lower tail under overload alone does not justify a default change.

With no background handshakes, all variants completed 1,000 foreground
requests/s with approximately 1.48–1.51 ms p99. Tako PSS was 64.52 MiB unchanged,
66.72 MiB with one thread and 67.30 MiB with two. Thus idle offload infrastructure
cost about 2–3 MiB here. Memory under overloaded traffic also depends on how many
requests and TLS states remain live; the lower PSS of the one-thread candidate
under load should not be generalized to all traffic.

## Identity, scope and validation

The free standard Ubuntu runner used the same original installer and real Go app
as the other diagnostics, within a shared **2 CPU quota, 8 GiB RAM, no swap**
container. Client, app and proxy share that quota. This runner differs from the
local profiling host and the buffer comparison jobs; never combine their
absolute RPS into one claimed optimization delta.

Pinned Tako: `f0ed5d938a4f26f4c775336c8f16aa572fe20dae`, Pingora 0.9.0, performance
head `2d7e16e440ee4a98a53464a6051391eed2a3dafe`, measured PR merge checkout
`cd21e679f905c0f3c57bf40a6595a3c009d63403`, Rust 1.99.1 and Go 1.26.3.
[Build identity](ci/build.txt) and [metadata](ci/metadata.json) preserve hashes
and limits. The unchanged control was built before applying the TLS-only patch.

The patch calls Pingora's existing
`TlsSettings::set_offload_threadpool(1, threads)` on ordinary TLS listeners. It
does not affect the custom PROXY-protocol listener or propose a user setting.
Offloading adds runtime scheduling and threads; it does not remove cryptographic
work. All 160 affected Tako proxy tests passed with offloading enabled; Go
fixture/client tests, local full-server smoke checks and workflow/syntax checks
also passed. See the [harness guide](../../diagnostics/tls-offload/README.md) and
profiling driver for reproduction.

No peak-throughput or HTTP/2 offload acceptance is claimed. The separate
[buffer report](../20261026-buffer-lifetime/README.md) contains the memory-saving
prototype and its unresolved performance checks. Neither experiment changes
production defaults or replaces the published release benchmark.
