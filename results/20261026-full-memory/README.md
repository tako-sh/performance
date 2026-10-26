# Full Tako memory investigation — 26 October 2026

Reducing the accepted-socket read buffer also reduces memory in the **complete
Tako server**, with a real deployed app and production Linux provisioning.
At 5,000 workers, the final two runs in reversed order measured **19.8% lower mean peak
PSS with 32 KiB** and **36.3% lower with 16 KiB**, relative to the 64 KiB default.
Every measured request in these eight cases returned 200, with no transport or
body-length errors.

| Proxy / accepted read buffer | Peak PSS, MiB (mean; range) | Mean requests/s | Change vs Tako 64 KiB |
| --- | ---: | ---: | ---: |
| Tako, 64 KiB | 766.9; 754.3–779.6 | 14,817 | baseline |
| Tako, 32 KiB | 615.4; 612.1–618.7 | 15,348 | −19.8% memory; +3.6% RPS |
| Tako, 16 KiB | 488.7; 453.2–524.2 | 14,743 | −36.3% memory; −0.5% RPS |
| Caddy 2.11.7 + rate-limit plugin | 769.0; 765.3–772.6 | 7,380 | control |

These are short experiments on one shared host. Two repetitions do not establish
statistical significance for small throughput differences. They support both
smaller buffers as candidates; they do not establish the best production default.
The initial 5k repeats measured reductions of 24.4% and 28.7% before the network
setup corrections. Peak memory varies with connection churn; all raw runs remain
available, and the final table uses the corrected harness consistently.

## Twenty thousand connections held open

This test exercises every TLS connection with 21 verified requests, limits work
to 64 requests in flight, and then holds all 20,000 connections open for ten
seconds. It measures connection retention rather than maximum throughput. The
table averages each run's median PSS during the holding phase, with two repeats.

| Proxy / accepted read buffer | Held PSS, MiB (mean; range) | Saving vs Tako 64 KiB |
| --- | ---: | ---: |
| Tako, 64 KiB | 2,257.4; 2,256.0–2,258.8 | baseline |
| Tako, 32 KiB | 1,634.1; 1,633.7–1,634.5 | 623.3 MiB / 27.6% |
| Tako, 16 KiB | 1,319.6; 1,318.9–1,320.4 | 937.8 MiB / 41.5% |
| Caddy 2.11.7 + rate-limit plugin | 1,022.8; 1,007.8–1,037.8 | control |

All tabled runs completed 420,000 successful requests each and verified 20,000
established connections while holding. Saving 32 KiB × 20,000 predicts 625 MiB;
saving 48 KiB × 20,000 predicts 937.5 MiB. The measured changes closely match.
That establishes a substantial accepted-socket buffer cost in the full server.

**The remaining gap is real in this workload:** even at 16 KiB, Tako retained
about 297 MiB more than Caddy (29%). The buffer change alone does not make Tako
the lower-memory implementation for all workloads. Per-connection Rust state,
native TLS allocations, and allocator retention need separate attribution before
claiming where the rest can be recovered.

The [Tako repeats](held/summary.json) all passed. The first version of the held
client marked its closing phase after closing sockets, causing one Caddy repeat
to count intentional connection teardown as a failure. The corrected client
marks closing first; both [fresh Caddy repeats](held-caddy/summary.json) passed
and supply the table's control. The original invalid sample is preserved.

## Free GitHub runner

The [corrected Actions run](https://github.com/tako-sh/performance/actions/runs/40278058403)
completed successfully, including all active and held cases, with zero failed
request or connection-count validations. Its [complete raw results](ci-passing/)
record the source/build identity and resource limits.

For the two active HTTP/1.1 small-response repeats at 5,000 workers:

| Configuration | Mean requests/s | Change vs unchanged Tako | Per-run p99 latency range, ms |
| --- | ---: | ---: | ---: |
| Tako, 64 KiB | 3,893 | baseline | 6,710–7,566 |
| Tako, 32 KiB | 3,830 | −1.6% | 7,395–7,514 |
| Tako, 16 KiB | 3,904 | +0.3% | 7,006–7,397 |
| Caddy | 2,751 | control | 7,086–7,277 |

Both candidates had about 39–42% higher throughput than Caddy in this workload. That does
not establish no slowdown against unchanged Tako. In particular, 32 KiB's mean
throughput was lower in this run, and the tail-latency ranges overlap. Two short
repeats cannot establish whether small differences are noise or regressions.
These saturated, closed-loop runs also include connection churn and share two
CPUs with the client; they do not replace latency tests at matched offered load.

**Acceptance requirement:** preserve current Tako throughput, tail latency and
CPU efficiency, and remain ahead of Caddy across the relevant workloads. Any
repeatable regression blocks a default change even if memory improves or Caddy
remains slower. Full-server bulk transfers and HTTP/2 remain unmeasured here.
Neither 32 KiB nor 16 KiB has cleared that requirement yet.

The [initial Actions run](https://github.com/tako-sh/performance/actions/runs/40275312582)
built the pinned binaries, passed the proxy tests, and reproduced the memory
reduction in Tako at 5k workers: 782.2 → 614.1 → 536.5 MiB for 64/32/16 KiB,
with all Tako requests returning 200. That is one pass, not a completed repeat.
Caddy returned 61 HTTP 502s, and the next case hit the listener-port collision
described below. The run failed and its [raw artifact data](ci-initial/summary.json)
is retained as incomplete evidence. The corrected workflow runs active 5k and
held 20k comparisons separately, as recorded in the successful replay above.

## Setup and measurement

- Linux x86-64; disposable container with 2 CPUs of quota, 8 GiB RAM, and no swap.
  The client, proxy, and one Go upstream share that quota. This is not the earlier
  dedicated VM and these are not replacement published capacity numbers.
- Tako `f0ed5d938a4f26f4c775336c8f16aa572fe20dae`, release build, one binary with
  the [benchmark-only patch](../../diagnostics/full-memory/tako-l4-buffer.patch).
  Rust 1.99.1, Go 1.26.3, mimalloc, OpenSSL, pinned Caddy dependency lockfile.
  The local build uses pyvips-binary 8.18.7; CI uses distribution libvips instead.
- TLS HTTP/1.1, 13-byte response, identical certificate and app response, 16
  loopback source IPs. Five seconds warmup, twenty nominal measurement seconds.
  Request draining can extend elapsed time. All variants retain their default
  behavior apart from the stated benchmark listener override and resource limits.
- PSS/RSS/private pages sampled every 250 ms for the proxy process only; client
  and app memory are excluded. The reported peak includes warmup and connection
  churn. Established connections on the TLS port are counted about every five
  seconds. The load generator closes idle connections between warmup and timing.
- Each case starts a new proxy process. Two passes use opposite variant order.
  Raw [final active results](active/summary.json), [environment](active/metadata.json),
  and [build identity](active/build.json) accompany the per-case samples.

## What failed at 20,000 workers

The initial 20k stress cases returned errors for both Tako and Caddy. They are
**not valid capacity or successful-memory comparisons**. The default ephemeral
range, 32768–60999, was exhausted by upstream connection churn; logs contain
`Cannot assign requested address`. Tako also marked its upstream unhealthy after
two-second health-check connection timeouts, causing 503s. Caddy returned 502s.

The initial series was stopped after the complete 5k repeats and five failed
20k cases. Completed cases are preserved; interrupted cases are excluded.
Sanitized per-case `diagnostics.json` files count selected runtime log events,
including warmup, without publishing build-machine paths.

The follow-up raises the private container's ephemeral range to 10240–65535 and
listen/SYN backlogs to 65535 for all proxies. It preserves Tako's health checks,
application behavior, and memory/CPU limits. Those settings are recorded in the
follow-up metadata. The [completed follow-up stress cases](stress/summary.json)
still show Tako health-check **read** timeouts under load, followed by 502/503s.
One Caddy case passed; its next case failed. These are still unsuitable for a
successful 20k capacity comparison.

That stress run also exposed a harness restart problem: the expanded ephemeral
range could borrow a public listener port. The final harness reserves 18080 and
18443 and gives Caddy a fresh upstream port per case to avoid cross-case socket
retention. The complete final 5k repeat validates that corrected setup. The 20k
saturation workload is an explicit optional CI input, not the default memory test.

## Other findings and remaining checks

Tako emits a per-request app log entry even when console logging is limited to
warnings. Its bounded 8,192-entry log queue drops entries at these request rates.
That behavior stayed enabled in every Tako case. Caddy's default access logging
is off, so the Caddy control compares these product configurations, not isolated
Rust-versus-Go runtime costs. Logging allocation and write batching deserve their
own experiment; these measurements do not quantify their memory contribution.

The smaller buffer saves memory held by accepted TCP connections. It is distinct
from HTTP body-buffer tuning and does not change upstream buffers or the custom
PROXY-protocol listener. Smaller transport reads can require more read operations
for large transfers. Full-server uploads/downloads, HTTP/2, long-duration retention,
and PROXY-protocol behavior remain prerequisites before selecting a new default.

Production Tako defaults and the main performance tables remain unchanged.
