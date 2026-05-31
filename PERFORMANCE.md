# Tako Proxy Performance

Date: 2026-05-31 UTC

This report is the public performance baseline for Tako against nginx and
Caddy. It intentionally omits exact hostnames, public IPs, private network
addresses, peer names, and user identifiers. The timed high-load path is
VM-local: load generator, proxy, and application all run on the same benchmark
VM, with TLS still enabled.

## Executive Summary

The latest post-release run used `tako-server 0.0.0-d81cc6d`. It includes the
request-metrics guard, disabled default response cache, and skipped Pingora's
default downstream compression module. The nginx configs were also equalized to
set `X-Forwarded-For` and `X-Forwarded-Proto`, matching the forwarding work
Tako and Caddy do.

Clean single-upstream HTTP/TLS rows:

| conc | nginx 200 rps | nginx p99 | Tako 200 rps | Tako p99 | Caddy 200 rps | Caddy p99 |
|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 23,445 | 98 ms | 16,408 | 152 ms | 7,926 | 204 ms |
| 2,500 | 17,824 | 495 ms | 14,916 | 509 ms | 7,055 | 2,236 ms |
| 5,000 | 12,446 | 1,251 ms | 12,977 | 2,647 ms | 6,138 | 4,801 ms |
| 7,500 | 9,984 | 2,511 ms | 11,059 | 4,903 ms | 4,820 | 7,878 ms |

Takeaways:

- Tako is still slower than nginx in the clean lower-load rows. At c2500, after
  equalizing forwarding headers, Tako is about 16% behind nginx on successful
  RPS with nearly identical p99.
- Tako clearly beats Caddy in this setup.
- Tako returns more successful responses than nginx at c5000 and c7500, but
  p99 latency is already in seconds. Treat those rows as overload behavior, not
  as the intended operating point.
- The 2 vCPU VM does not reach 60k-100k clean TLS RPS. CPU is saturated across
  the heavy rows, and proxy/app/loadgen all share the same machine.
- Load-balanced mode is intentionally excluded for this exe-node result set.
  Four app processes on a 2 vCPU VM mostly measure process contention; use a
  larger or multi-node testbed for load-balancer results.

## Latest HTTP Rerun

Raw HTTP data: `results/20260531T171211Z/http-vm-local`  
HTTP graphs: `results/20260531T171211Z/http-vm-local/graphs/README.md`

![HTTP 200 RPS by concurrency](results/20260531T171211Z/http-vm-local/graphs/throughput-200-rps.svg)

![p99 latency by concurrency](results/20260531T171211Z/http-vm-local/graphs/p99-latency-ms.svg)

![Non-200 response rate by concurrency](results/20260531T171211Z/http-vm-local/graphs/non-200-rate.svg)

![Client error rate by concurrency](results/20260531T171211Z/http-vm-local/graphs/client-error-rate.svg)

### HTTP Results

| case | conc | 200 rps | p50 ms | p99 ms | non-200 | client errors | status |
|---|---:|---:|---:|---:|---:|---:|---|
| nginx-single | 1,000 | 23,445 | 37 | 98 | 0.00% | 0.00% | 200:703703 |
| tako-single | 1,000 | 16,408 | 59 | 152 | 0.00% | 0.00% | 200:492953 |
| caddy-single | 1,000 | 7,926 | 124 | 204 | 0.00% | 0.00% | 200:238386 |
| nginx-single | 2,500 | 17,824 | 112 | 495 | 0.00% | 0.00% | 200:535896 |
| tako-single | 2,500 | 14,916 | 181 | 509 | 0.00% | 0.00% | 200:449728 |
| caddy-single | 2,500 | 7,055 | 341 | 2,236 | 0.00% | 0.00% | 200:213072 |
| nginx-single | 5,000 | 12,446 | 291 | 1,251 | 0.00% | 0.00% | 200:375311 |
| tako-single | 5,000 | 12,977 | 421 | 2,647 | 0.00% | 0.00% | 200:393011 |
| caddy-single | 5,000 | 6,138 | 720 | 4,801 | 0.06% | 0.00% | 200:187534, 502:113 |
| nginx-single | 7,500 | 9,984 | 472 | 2,511 | 0.00% | 0.00% | 200:304114 |
| tako-single | 7,500 | 11,059 | 666 | 4,903 | 0.00% | 0.00% | 200:336593 |
| caddy-single | 7,500 | 4,820 | 1,105 | 7,878 | 0.00% | 0.04% | 200:147838 |
| nginx-single | 10,000 | 6,539 | 962 | 4,537 | 0.00% | 0.00% | 200:228106 |
| tako-single | 10,000 | 5,316 | 1,295 | 9,270 | 0.00% | 2.58% | 200:166348 |
| caddy-single | 10,000 | 3,003 | 2,446 | 9,802 | 0.00% | 2.56% | 200:92657 |
| nginx-single | 15,000 | 2,280 | 3,497 | 9,817 | 0.00% | 33.18% | 200:83567 |
| tako-single | 15,000 | 4,488 | 2,081 | 10,230 | 0.00% | 5.22% | 200:140341 |
| caddy-single | 15,000 | 206 | 8,458 | 9,799 | 7.44% | 83.05% | 200:7662, 502:616 |
| nginx-single | 20,000 | 2,448 | 4,438 | 10,191 | 0.00% | 24.76% | 200:85835 |
| tako-single | 20,000 | 2,832 | 4,617 | 9,784 | 0.00% | 17.55% | 200:93573 |
| caddy-single | 20,000 | 135 | 8,780 | 9,621 | 9.15% | 91.10% | 200:5101, 502:514 |

### Resource Highlights

The per-test SVGs now include CPU, proxy/app RSS, total memory, and TLS
connection samples. In these graphs, 100% CPU means the whole 2 vCPU VM is
busy, not one core.

| case | conc | max CPU | proxy RSS | app RSS | max TLS conns |
|---|---:|---:|---:|---:|---:|
| nginx-single | 1,000 | 99.1% | 103 MiB | 40 MiB | 3,042 |
| tako-single | 1,000 | 100.0% | 211 MiB | 39 MiB | 1,188 |
| caddy-single | 1,000 | 100.0% | 193 MiB | 50 MiB | 1,037 |
| nginx-single | 2,500 | 100.0% | 168 MiB | 61 MiB | 8,219 |
| tako-single | 2,500 | 100.0% | 446 MiB | 71 MiB | 2,954 |
| caddy-single | 2,500 | 100.0% | 382 MiB | 102 MiB | 2,804 |
| nginx-single | 5,000 | 100.0% | 271 MiB | 119 MiB | 15,118 |
| tako-single | 5,000 | 100.0% | 844 MiB | 124 MiB | 6,045 |
| caddy-single | 5,000 | 100.0% | 691 MiB | 136 MiB | 8,221 |
| nginx-single | 7,500 | 100.0% | 333 MiB | 105 MiB | 15,327 |
| tako-single | 7,500 | 100.0% | 1,362 MiB | 169 MiB | 11,326 |
| caddy-single | 7,500 | 100.0% | 1,058 MiB | 139 MiB | 12,463 |
| nginx-single | 10,000 | 100.0% | 437 MiB | 120 MiB | 15,822 |
| tako-single | 10,000 | 100.0% | 2,129 MiB | 199 MiB | 21,624 |
| caddy-single | 10,000 | 100.0% | 1,484 MiB | 137 MiB | 20,400 |
| nginx-single | 15,000 | 100.0% | 576 MiB | 117 MiB | 15,470 |
| tako-single | 15,000 | 100.0% | 2,368 MiB | 299 MiB | 24,332 |
| caddy-single | 15,000 | 100.0% | 1,073 MiB | 125 MiB | 15,007 |
| nginx-single | 20,000 | 100.0% | 490 MiB | 119 MiB | 15,766 |
| tako-single | 20,000 | 100.0% | 1,926 MiB | 213 MiB | 23,451 |
| caddy-single | 20,000 | 100.0% | 1,224 MiB | 132 MiB | 15,448 |

Tako's proxy RSS is materially higher than nginx in every heavy row. That is a
separate optimization target from raw RPS.

## Channels And Workflows

Raw channel/workflow data:
`results/20260531T173340Z/tako-features-vm-local`  
Channel/workflow graphs:
`results/20260531T173340Z/tako-features-vm-local/graphs/README.md`

These rows use the same released `tako-server 0.0.0-d81cc6d`, same VM-local
HTTPS path, and a single Tako app instance. The endpoints are implemented with
the JavaScript SDK:

- `/channel-publish`: publishes one message to a `feed` channel.
- `/workflow-enqueue`: enqueues one `noop` workflow payload.

![Channel/workflow HTTP 200 RPS by concurrency](results/20260531T173340Z/tako-features-vm-local/graphs/throughput-200-rps.svg)

![Channel/workflow p99 latency by concurrency](results/20260531T173340Z/tako-features-vm-local/graphs/p99-latency-ms.svg)

![Channel/workflow non-200 response rate](results/20260531T173340Z/tako-features-vm-local/graphs/non-200-rate.svg)

![Channel/workflow client error rate](results/20260531T173340Z/tako-features-vm-local/graphs/client-error-rate.svg)

| case | conc | 200 rps | p50 ms | p99 ms | non-200 | client errors | status |
|---|---:|---:|---:|---:|---:|---:|---|
| channel-publish | 500 | 7,184 | 68 | 137 | 0.00% | 0.00% | 200:215870 |
| workflow-enqueue | 500 | 5,785 | 87 | 165 | 0.00% | 0.00% | 200:173926 |
| channel-publish | 1,000 | 6,920 | 145 | 259 | 0.00% | 0.00% | 200:208549 |
| workflow-enqueue | 1,000 | 5,408 | 181 | 457 | 0.00% | 0.00% | 200:163294 |
| channel-publish | 2,000 | 6,849 | 295 | 720 | 0.00% | 0.00% | 200:207233 |
| workflow-enqueue | 2,000 | 5,208 | 384 | 1,288 | 0.00% | 0.00% | 200:158108 |
| channel-publish | 4,000 | 6,294 | 614 | 2,638 | 0.00% | 0.00% | 200:192168 |
| workflow-enqueue | 4,000 | 4,843 | 802 | 3,411 | 0.00% | 0.00% | 200:148438 |
| channel-publish | 8,000 | 3,034 | 1,710 | 9,419 | 9.62% | 1.44% | 200:96104, 502:9752, 503:482 |
| workflow-enqueue | 8,000 | 2,048 | 2,033 | 9,438 | 12.36% | 5.01% | 200:64252, 502:9065 |

Channel publish and workflow enqueue are clean through c4000 in this setup.
c8000 is failure mode for both paths. The sampler change that includes Bun app
RSS was added after this run, so use proxy RSS and total memory graphs for this
feature result; app RSS is not comparable in these specific feature CSVs.

## Why Tako Still Trails Nginx

Nginx is a static reverse proxy in this benchmark. Tako is doing product-level
work on the request path that nginx is not configured to do:

- Request routing reads the shared route table and selects an app from the Host
  and path on every request (`tako-server/src/proxy/service/mod.rs:121`,
  `tako-server/src/proxy/service/mod.rs:125`).
- Route selection returns owned `String` values for the app and matched route
  path (`tako-server/src/routing.rs:154`). This allocates/clones per request.
- The per-IP request limiter does a `DashMap` entry lookup and atomic
  increment/release for every proxied request (`tako-server/src/proxy/limits.rs:19`,
  `tako-server/src/proxy/limits.rs:33`). This is useful protection, but the
  comparison nginx/Caddy configs do not have equivalent per-IP limiting.
- The proxy checks image, channel, and static-asset handlers before falling
  through to upstream proxying (`tako-server/src/proxy/service/mod.rs:274`,
  `tako-server/src/proxy/service/mod.rs:289`,
  `tako-server/src/proxy/service/mod.rs:296`).
- Backend resolution does a `DashMap` app lookup, a round-robin atomic, and
  healthy-instance selection (`tako-server/src/lb/mod.rs:65`). The active-set
  change removed the old per-request health scan, but the path is still heavier
  than nginx's static upstream selection.
- Backend request accounting increments per-instance counters around every
  proxied request (`tako-server/src/proxy/service/mod.rs:466`).
- Header work is intentionally stricter: Tako sets `X-Forwarded-Proto`, sets or
  strips `X-Forwarded-For`, and strips `Forwarded` and
  `X-Tako-Internal-Token` (`tako-server/src/proxy/service/mod.rs:444`).

The best next targets are:

- Replace the async route-table read on the hot path with a synchronous or
  lock-free route snapshot.
- Return `Arc<str>` or references from route selection to avoid cloning app and
  route strings per request.
- Optimize or make configurable the per-IP limiter path for trusted internal
  benchmark routes, or configure equivalent limits in nginx/Caddy when testing
  the protected production path.
- Reduce proxy RSS under high concurrency by profiling connection/session
  allocation and Pingora upstream peer construction.
- Run `perf` or flamegraph comparisons on a larger box or with an external
  load generator so the load generator does not share the same 2 vCPU budget.

## Test Host And Network

### Load Generator

- OS: macOS Darwin 25.5.0 arm64
- CPU count: 10
- Memory: 16 GiB
- Pre-run desktop load was checked; no local process was consuming excessive
  CPU or memory.

### Server

- OS: Ubuntu 24.04.4 LTS, Linux 6.12.90, x86_64
- VM: KVM
- CPU: 2 vCPU, AMD EPYC 9554P 64-Core Processor
- Memory: 7.8 GiB, no swap
- Disk: 25 GiB root filesystem
- Region observed from public geolocation: Tokyo, Japan
- Mac-to-VM public endpoint ping before the high-load run: about 72 ms average,
  0% packet loss

The public web access URL was not used for timed proxy comparison because it
would measure an access layer outside Tako/nginx/Caddy. The controlled route
for timed HTTP tests was:

```text
https://bench.test:18443/
Host/SNI: bench.test
Resolved to: 127.0.0.1 on the benchmark VM
TLS: same self-signed certificate for every proxy
```

## Software Versions

- Tako release used for latest HTTP and feature reruns:
  `tako-server 0.0.0-d81cc6d`
- nginx: `nginx/1.24.0 (Ubuntu)`
- Caddy: `2.6.2`
- Go on VM: `go1.26.3 linux/amd64`

Intermediate Tako releases preserved in result directories:

- `0.0.0-f1d70e9`: metrics-disabled request path
- `0.0.0-660a696`: default response cache disabled
- `0.0.0-d81cc6d`: default compression module skipped

## Applications

### HTTP App

The HTTP comparison uses `cmd/benchapp`, a small Go application with identical
payloads behind all three proxies:

- `/plaintext`: `hello, world\n`, fixed `Content-Length: 13`
- `/json`: `{"message":"hello","ok":true}\n`
- `/status`: internal Tako health check endpoint when `Host: bench-http.tako`
- `/pid`: instance metadata for manual checks

Nginx and Caddy start the same Go binary on loopback ports. Tako runs the same
binary as a deployed app from the benchmark VM's Tako data directory.

### Channels And Workflows App

The feature benchmark uses `apps/channels-workflows`, a small Bun/Tako SDK app:

- `/channel-publish`: `feed.publish({ type: "tick", data: ... })`
- `/workflow-enqueue`: `noop.enqueue({ seq, at })`
- `/status`: JSON health response

The workflow handler performs one persisted `ctx.run("ack", ...)` step and
returns immediately.

## Methodology

- One route and TLS certificate were used for all HTTP proxy comparisons:
  `bench.test:18443`.
- The load generator resolves `bench.test:18443` to `127.0.0.1` on the VM and
  sets both Host and SNI to `bench.test`.
- TLS verification is disabled because the certificate is self-signed, but TLS
  is still active for every proxy.
- HTTP/2 is disabled in the load generator, so the comparison is HTTP/1.1 over
  TLS.
- Each timed case has a 10 second warmup followed by a 30 second measurement
  window.
- Single mode uses one upstream instance.
- Tako runs with `--metrics-port 0` and `--no-acme` during proxy comparison.
- High-concurrency runs use 16 loopback source IPs, `127.0.0.2` through
  `127.0.0.17`, to avoid turning Tako's default 2048 concurrent request cap per
  source IP into the benchmark bottleneck.
- Metrics are sampled once per second from `/proc` on the VM: total CPU,
  memory used/available, aggregate app RSS, aggregate proxy RSS, and established
  TLS connections.

This is not a pure proxy microbenchmark because the load generator, proxy, and
app processes all share the same 2 vCPU VM. It is a useful "what can this one
VM produce end-to-end?" benchmark.

## Historical Data

Older result directories are kept for comparison and regression analysis:

- `results/20260531T113110Z/http-vm-local`: active-set release rerun.
- `results/20260531T120513Z/tako-features-vm-local`: active-set feature rerun.
- `results/20260531T153937Z/http-vm-local`: metrics-disabled release rerun.
- `results/20260531T163148Z/http-vm-local`: response-cache-disabled rerun.
- `results/20260531T171211Z/http-vm-local`: latest release HTTP rerun.
- `results/20260531T173340Z/tako-features-vm-local`: latest release feature
  rerun.

## Reproducing

Sync the repo to the VM, install the current Tako release as
`/usr/local/bin/tako-server`, then run:

```bash
BENCH_VM=<ssh-host> \
SOURCE_IPS='127.0.0.2,127.0.0.3,127.0.0.4,127.0.0.5,127.0.0.6,127.0.0.7,127.0.0.8,127.0.0.9,127.0.0.10,127.0.0.11,127.0.0.12,127.0.0.13,127.0.0.14,127.0.0.15,127.0.0.16,127.0.0.17' \
CONCURRENCY_LIST='1000 2500 5000 7500 10000 15000 20000' \
WARMUP=10s \
DURATION=30s \
METRICS_INTERVAL=1 \
METRICS_CONNECTIONS=1 \
MODES=single \
ENDPOINTS=plaintext \
./scripts/run-vm-local-http-benchmarks.sh
```

Feature endpoints:

```bash
BENCH_VM=<ssh-host> \
SOURCE_IPS='127.0.0.2,127.0.0.3,127.0.0.4,127.0.0.5,127.0.0.6,127.0.0.7,127.0.0.8,127.0.0.9,127.0.0.10,127.0.0.11,127.0.0.12,127.0.0.13,127.0.0.14,127.0.0.15,127.0.0.16,127.0.0.17' \
CONCURRENCY_LIST='500 1000 2000 4000 8000' \
WARMUP=10s \
DURATION=30s \
METRICS_INTERVAL=1 \
METRICS_CONNECTIONS=1 \
./scripts/run-vm-local-tako-feature-benchmarks.sh
```

Regenerate graphs after editing result CSVs or the graph renderer:

```bash
./scripts/render-metrics-graphs.sh results/<timestamp>/http-vm-local
./scripts/render-metrics-graphs.sh results/<timestamp>/tako-features-vm-local
```
