# Tako Proxy Performance Baseline

Date: 2026-05-31 UTC

This is the first repeatable baseline for Tako against nginx and Caddy on the
benchmark VM. It includes both a laptop-driven run over Tailscale and a
VM-local high-load run, using the same TLS route, certificate, application
payloads, and load generator for each proxy. Exact hostnames, public IPs,
private Tailscale IPs, MagicDNS suffixes, peer names, and user identifiers are
intentionally omitted from this public report.

## Executive Summary

At 500 concurrent HTTP/1.1 clients over TLS from the laptop, nginx was the
fastest HTTP proxy. Tako single-instance trailed nginx single-instance by about
7.4% on both plaintext and JSON responses, and was much faster than Caddy in
this environment.

A VM-local high-load pass was added to find the ceiling of the single 2 vCPU
VM. With TLS, the same app, and load generation running on the VM itself, the
best clean 200-throughput was:

- nginx single: 27,694 rps at c100, p99 9 ms
- Tako single: 21,205 rps at c100, p99 10 ms
- Caddy load-balanced: 13,683 rps at c100, p99 20 ms

The VM did not get close to 60k-100k clean TLS rps under these conditions. The
machine saturates before that: by c500-c1000 the load generator, proxy, and app
are sharing the full 2 vCPU budget. At overload levels, source-sharded Tako
does better than nginx on clean 200 rps at c2500 and c5000, but p99 latency is
already hundreds of milliseconds to seconds, so those are not good steady-state
targets.

The first high-load Tako runs returned many 429 responses above c2048 because
Tako has a built-in per-client-IP concurrent request cap. A final source-sharded
run used 16 loopback source IPs so the c2500+ rows measure proxy capacity
rather than the per-IP limiter.

The channel and workflow benchmark initially failed on the released
`tako-server 0.0.0-ea3eb66` because app processes could not use the internal
workflow/channel Unix socket. A source fix was implemented and validated with a
patched VM-native `tako-server` build. With the patched binary, channel publish
and workflow enqueue both completed with only HTTP 200 responses.

## Test Host And Network

### Load Generator

- OS: macOS Darwin 25.5.0 arm64
- CPU count: 10
- Memory: 16 GiB
- Load snapshot before the feature benchmark: normal desktop/Codex background
  load; no process near 200% CPU or high memory.

### Server

- OS: Ubuntu 24.04.4 LTS, Linux 6.12.90, x86_64
- VM: KVM
- CPU: 2 vCPU, AMD EPYC 9554P 64-Core Processor
- Memory: 7.8 GiB, no swap
- Disk: 25 GiB root filesystem
- Tailscale relay: `tok`
- Direct public address geolocation: Tokyo, Japan, AS396356 Latitude.sh
- Public access hostname geolocation: Berkeley, CA, AS402146 Bold Software Inc,
  anycast

The public access URL was not used for the timed proxy comparison because it
redirected to an `exe.dev` login gate. Benchmarking that URL would measure the
public access layer rather than Tako, nginx, or Caddy directly. The controlled
route was:

```text
https://bench.test:18443/
Host/SNI: bench.test
Resolved to: private Tailscale address
TLS: same self-signed certificate for every proxy
```

Ping from the laptop:

| target | min ms | avg ms | max ms | stddev ms | loss |
|---|---:|---:|---:|---:|---:|
| private Tailscale route | 28.087 | 32.591 | 64.541 | 7.489 | 0% |
| public access hostname | 69.118 | 70.684 | 73.740 | 1.205 | 0% |

## Software Versions

- Tako release used for HTTP proxy comparison: `tako-server 0.0.0-ea3eb66`
- Patched Tako binary used for valid channel/workflow benchmark:
  `tako-server 0.0.0`, built on the VM from local source
- nginx: `nginx/1.24.0 (Ubuntu)`
- Caddy: `2.6.2`
- Go on VM: `go1.26.3 linux/amd64`
- Tailscale on VM: `1.98.4-t9e69045b2-ged3a62f14`

## Applications

### HTTP App

The HTTP comparison uses `cmd/benchapp`, a small Go application with identical
payloads behind all three proxies:

- `/plaintext`: `hello, world\n`, fixed `Content-Length: 13`
- `/json`: `{"message":"hello","ok":true}\n`
- `/status`: internal Tako health check endpoint when `Host: bench-http.tako`
- `/pid`: instance metadata for manual checks

Manual nginx and Caddy runs start the same Go binary on loopback ports. Tako
runs the same binary as a deployed app from:

```text
/opt/tako-performance/tako-data/apps/bench-http/production/releases/baseline-001
```

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
- The load generator resolves `bench.test:18443` to the Tailscale IP and sets
  both Host and SNI to `bench.test`.
- TLS verification is disabled because the certificate is self-signed, but TLS
  is still active for every proxy.
- HTTP/2 is disabled in the load generator, so the comparison is HTTP/1.1 over
  TLS.
- Each timed case has a 5 second warmup followed by a 30 second measurement
  window.
- Single mode uses one upstream instance.
- Load-balanced mode uses four upstream instances:
  - nginx: upstream ports `9101` through `9104`
  - Caddy: upstream ports `9101` through `9104`
  - Tako: app scaled to four instances

Because the load generator is the laptop and the VM is in Tokyo, the `c=100`
run is mostly RTT/concurrency limited. The `c=500` run is more useful for proxy
comparison, but still includes real Tailscale and cross-network overhead.

The VM-local high-load runs use the same TLS certificate, Host/SNI, HTTP app,
and proxy configs, but the load generator runs on the VM and resolves
`bench.test:18443` to `127.0.0.1`. Tailscale is not in the measured HTTP path
for these runs; it is only used for SSH orchestration and result collection.
This is not a pure proxy microbenchmark because the load generator, proxy, and
app processes all share the same 2 vCPU VM.

The final high-load run used 16 loopback source IPs:

```text
127.0.0.2 through 127.0.0.17
```

That avoids measuring Tako's per-client-IP DDoS limiter when concurrency is
above 2048. A separate single-source diagnostic run is kept to show that limiter
behavior.

Metrics were sampled once per second from `/proc` on the VM:

- total CPU utilization
- memory used and available
- aggregate benchmark app RSS
- aggregate proxy RSS

Connection counting is disabled in the final run because enumerating thousands
of sockets with `ss` showed measurable CPU overhead at very high concurrency.

## HTTP Results: 100 Concurrent Clients

Raw data: `results/20260531T043913Z/http`

| case | rps | mean ms | p95 ms | p99 ms | errors | status |
|---|---:|---:|---:|---:|---:|---|
| caddy-lb-json-c100 | 2742.56 | 36.42 | 48.27 | 57.61 | 0 | 200:82368 |
| caddy-lb-plaintext-c100 | 2721.32 | 36.71 | 48.52 | 58.28 | 0 | 200:81700 |
| caddy-single-json-c100 | 2653.42 | 37.65 | 49.29 | 60.02 | 0 | 200:79703 |
| caddy-single-plaintext-c100 | 2698.53 | 37.01 | 49.36 | 57.27 | 0 | 200:81036 |
| nginx-lb-json-c100 | 2755.39 | 36.25 | 44.95 | 51.23 | 0 | 200:82752 |
| nginx-lb-plaintext-c100 | 2743.73 | 36.4 | 45.78 | 51.24 | 0 | 200:82410 |
| nginx-single-json-c100 | 2720.52 | 36.72 | 45.17 | 51.83 | 0 | 200:81734 |
| nginx-single-plaintext-c100 | 2740.66 | 36.43 | 44.62 | 50.88 | 0 | 200:82324 |
| tako-lb-json-c100 | 2736.23 | 36.5 | 46.14 | 51.15 | 0 | 200:82185 |
| tako-lb-plaintext-c100 | 2649.75 | 37.71 | 49.87 | 59.33 | 0 | 200:79575 |
| tako-single-json-c100 | 2768.7 | 36.08 | 44.97 | 50.53 | 0 | 200:83138 |
| tako-single-plaintext-c100 | 2731.22 | 36.56 | 45.06 | 51.8 | 0 | 200:82072 |

At this concurrency, all three proxies cluster around 2.6-2.8k requests/sec.
That matches the RTT limit: `100 / ~36ms` is roughly 2.8k requests/sec.

## HTTP Results: 500 Concurrent Clients

Raw data: `results/20260531T045015Z/http`

| case | rps | mean ms | p95 ms | p99 ms | errors | status |
|---|---:|---:|---:|---:|---:|---|
| caddy-lb-json-c500 | 5408.8 | 92.3 | 139.02 | 166.91 | 0 | 200:162588 |
| caddy-lb-plaintext-c500 | 5361.73 | 93.1 | 140.98 | 164.14 | 0 | 200:161333 |
| caddy-single-json-c500 | 5733.18 | 87.05 | 129.26 | 151.82 | 0 | 200:172383 |
| caddy-single-plaintext-c500 | 5980.57 | 83.49 | 129.68 | 206.95 | 0 | 200:179811 |
| nginx-lb-json-c500 | 12586.27 | 39.64 | 54.31 | 73.55 | 0 | 200:378012 |
| nginx-lb-plaintext-c500 | 12804.48 | 38.97 | 52.7 | 76.03 | 0 | 200:384651 |
| nginx-single-json-c500 | 13567.68 | 36.78 | 45.44 | 63.53 | 0 | 200:407489 |
| nginx-single-plaintext-c500 | 13691.31 | 36.45 | 45.04 | 64.56 | 0 | 200:411206 |
| tako-lb-json-c500 | 10159.38 | 49.15 | 72.15 | 84.32 | 0 | 200:305170 |
| tako-lb-plaintext-c500 | 10229.89 | 48.82 | 70.15 | 82.3 | 0 | 200:307214 |
| tako-single-json-c500 | 12571.87 | 39.7 | 52.05 | 60.87 | 0 | 200:377592 |
| tako-single-plaintext-c500 | 12675.96 | 39.37 | 50.51 | 59.79 | 0 | 200:380687 |

Key comparisons from the 500-concurrency run:

- Tako single plaintext: 12,675.96 rps, 7.4% below nginx single plaintext.
- Tako single JSON: 12,571.87 rps, 7.3% below nginx single JSON.
- Tako load-balanced plaintext: 10,229.89 rps, 20.1% below nginx
  load-balanced plaintext.
- Tako load-balanced JSON: 10,159.38 rps, 19.3% below nginx load-balanced
  JSON.
- Tako single plaintext was about 112% faster than Caddy single plaintext.
- Tako load-balanced plaintext was about 91% faster than Caddy load-balanced
  plaintext.

## VM-Local High-Load Results

Raw final data: `results/20260531T083525Z/http-vm-local`

CPU/RAM graphs: `results/20260531T083525Z/http-vm-local/graphs`

This run keeps TLS enabled but removes laptop-to-VM network latency from the
request path. The load generator runs on the same VM as the proxy and app, so
the result is the total throughput the single VM can produce end-to-end.

The final pass used 16 loopback source IPs. This matters for Tako because its
default per-client-IP concurrent request cap is 2048. The single-source
diagnostic run, `results/20260531T081058Z/http-vm-local`, reproduced that
behavior: at c2500 and c5000, Tako returned many 429 responses. The
source-sharded run below avoids that artifact and is the fairer high-concurrency
comparison.

| case | conc | source IPs | rps | 200 rps | errors | p99 ms | status |
|---|---:|---:|---:|---:|---:|---:|---|
| caddy-lb-plaintext-c100 | 100 | 16 | 13,683 | 13,683 | 0 | 20 | 200:273725 |
| caddy-single-plaintext-c100 | 100 | 16 | 12,128 | 12,128 | 0 | 21 | 200:242615 |
| nginx-lb-plaintext-c100 | 100 | 16 | 25,329 | 25,329 | 0 | 10 | 200:506653 |
| nginx-single-plaintext-c100 | 100 | 16 | 27,694 | 27,694 | 0 | 9 | 200:553921 |
| tako-lb-plaintext-c100 | 100 | 16 | 18,402 | 18,402 | 0 | 11 | 200:368165 |
| tako-single-plaintext-c100 | 100 | 16 | 21,205 | 21,205 | 0 | 10 | 200:424182 |
| caddy-lb-plaintext-c500 | 500 | 16 | 9,407 | 9,407 | 0 | 101 | 200:188588 |
| caddy-single-plaintext-c500 | 500 | 16 | 8,962 | 8,962 | 0 | 103 | 200:179608 |
| nginx-lb-plaintext-c500 | 500 | 16 | 24,624 | 24,624 | 0 | 45 | 200:495630 |
| nginx-single-plaintext-c500 | 500 | 16 | 27,472 | 27,472 | 0 | 43 | 200:549607 |
| tako-lb-plaintext-c500 | 500 | 16 | 15,530 | 15,530 | 0 | 93 | 200:311058 |
| tako-single-plaintext-c500 | 500 | 16 | 17,977 | 17,977 | 0 | 84 | 200:359914 |
| caddy-lb-plaintext-c1000 | 1000 | 16 | 7,689 | 7,689 | 0 | 216 | 200:154618 |
| caddy-single-plaintext-c1000 | 1000 | 16 | 7,857 | 7,857 | 0 | 207 | 200:157659 |
| nginx-lb-plaintext-c1000 | 1000 | 16 | 19,306 | 19,306 | 0 | 169 | 200:386861 |
| nginx-single-plaintext-c1000 | 1000 | 16 | 24,211 | 24,211 | 0 | 85 | 200:485030 |
| tako-lb-plaintext-c1000 | 1000 | 16 | 14,255 | 14,255 | 0 | 325 | 200:285655 |
| tako-single-plaintext-c1000 | 1000 | 16 | 16,270 | 16,270 | 0 | 262 | 200:326102 |
| caddy-lb-plaintext-c2500 | 2500 | 16 | 6,035 | 6,035 | 0 | 2,434 | 200:122354 |
| caddy-single-plaintext-c2500 | 2500 | 16 | 6,860 | 6,860 | 0 | 2,305 | 200:138615 |
| nginx-lb-plaintext-c2500 | 2500 | 16 | 11,390 | 11,390 | 0 | 752 | 200:229346 |
| nginx-single-plaintext-c2500 | 2500 | 16 | 13,867 | 13,867 | 0 | 585 | 200:278468 |
| tako-lb-plaintext-c2500 | 2500 | 16 | 12,506 | 12,506 | 0 | 1,338 | 200:251868 |
| tako-single-plaintext-c2500 | 2500 | 16 | 14,379 | 14,379 | 0 | 876 | 200:289340 |
| caddy-lb-plaintext-c5000 | 5000 | 16 | 5,136 | 5,136 | 0 | 5,056 | 200:105292 |
| caddy-single-plaintext-c5000 | 5000 | 16 | 5,902 | 5,898 | 0 | 4,882 | 200:121336, 502:84 |
| nginx-lb-plaintext-c5000 | 5000 | 16 | 9,854 | 9,854 | 0 | 1,449 | 200:200016 |
| nginx-single-plaintext-c5000 | 5000 | 16 | 10,544 | 10,544 | 0 | 1,563 | 200:212829 |
| tako-lb-plaintext-c5000 | 5000 | 16 | 10,681 | 10,681 | 0 | 4,046 | 200:216471 |
| tako-single-plaintext-c5000 | 5000 | 16 | 12,446 | 12,446 | 0 | 3,753 | 200:252142 |
| caddy-lb-plaintext-c10000 | 10000 | 16 | 1,571 | 1,571 | 1,666 | 9,473 | 200:36325 |
| caddy-single-plaintext-c10000 | 10000 | 16 | 1,599 | 1,540 | 3,952 | 9,885 | 200:36945, 502:1424 |
| nginx-lb-plaintext-c10000 | 10000 | 16 | 6,303 | 6,303 | 0 | 3,625 | 200:128534 |
| nginx-single-plaintext-c10000 | 10000 | 16 | 4,302 | 4,302 | 0 | 5,673 | 200:88449 |
| tako-lb-plaintext-c10000 | 10000 | 16 | 6,184 | 6,184 | 5,029 | 7,435 | 200:127575 |
| tako-single-plaintext-c10000 | 10000 | 16 | 7,476 | 7,476 | 2,548 | 8,633 | 200:154736 |

Interpretation:

- The practical low-latency ceiling is below 60k-100k rps on this 2 vCPU VM.
  The best clean row is nginx single at 27.7k rps with p99 9 ms.
- Tako single peaks at 21.2k rps in the low-latency range. At c2500 and c5000,
  Tako's clean 200 rps beats nginx, but p99 latency is already too high for a
  healthy steady-state target.
- Load balancing does not help the benchmark app on this VM. Four app
  processes compete for the same 2 vCPUs, and every proxy's LB mode is slower
  than its single-instance mode until overload changes the shape of queueing.
- c10000 is failure-mode data. It shows how each proxy behaves under extreme
  overload, not a target operating point.

### VM-Local Resource Summary

| case | max CPU % | max memory GiB | max proxy RSS MiB | max app RSS MiB |
|---|---:|---:|---:|---:|
| nginx-single-c500 | 98.1 | 0.42 | 61 | 30 |
| tako-single-c500 | 94.1 | 0.45 | 140 | 25 |
| caddy-single-c500 | 100.0 | 0.45 | 138 | 30 |
| nginx-single-c2500 | 100.0 | 1.27 | 177 | 56 |
| tako-single-c2500 | 94.7 | 0.85 | 361 | 35 |
| caddy-single-c2500 | 100.0 | 0.91 | 351 | 104 |
| nginx-single-c5000 | 100.0 | 1.88 | 283 | 81 |
| tako-single-c5000 | 95.2 | 1.44 | 730 | 32 |
| caddy-single-c5000 | 100.0 | 1.40 | 608 | 134 |
| nginx-lb-c5000 | 100.0 | 1.96 | 268 | 114 |
| tako-lb-c5000 | 94.7 | 1.42 | 724 | 62 |
| caddy-lb-c5000 | 100.0 | 1.43 | 602 | 214 |
| nginx-single-c10000 | 100.0 | 2.65 | 398 | 90 |
| tako-single-c10000 | 99.0 | 2.41 | 1,434 | 34 |
| caddy-single-c10000 | 100.0 | 2.55 | 1,278 | 135 |

Example graphs:

- `results/20260531T083525Z/http-vm-local/graphs/nginx-single-plaintext-c500.svg`
- `results/20260531T083525Z/http-vm-local/graphs/tako-single-plaintext-c500.svg`
- `results/20260531T083525Z/http-vm-local/graphs/nginx-single-plaintext-c2500.svg`
- `results/20260531T083525Z/http-vm-local/graphs/tako-single-plaintext-c2500.svg`
- `results/20260531T083525Z/http-vm-local/graphs/tako-single-plaintext-c5000.svg`

## Channel And Workflow Results

Raw valid data: `results/20260531T053951Z/tako-features`

These were run with the patched VM-native `tako-server` build because the
released server failed the first feature attempt. The client sent 50 concurrent
POST requests, with the same TLS route and network path as the HTTP proxy tests.

| case | rps | mean ms | p95 ms | p99 ms | errors | status |
|---|---:|---:|---:|---:|---:|---|
| tako-feature-channel-publish-c50 | 1310.81 | 38.11 | 52.59 | 63.57 | 0 | 200:39380 |
| tako-feature-workflow-enqueue-c50 | 1100.17 | 45.41 | 65.29 | 72.81 | 0 | 200:33054 |

The invalid first attempt is preserved in
`results/20260531T050527Z/tako-features`. It returned only 502/503 responses
and is excluded from the performance result. That run exposed the internal
socket problem fixed in the source tree.

## Findings

1. Tako's normal single-instance proxy path is reasonably close to nginx in
   this cross-network TLS run. The measured gap was about 7.4% at 500
   concurrency.
2. In the VM-local high-load run, the single VM did not approach 60k-100k clean
   TLS rps. The best clean low-latency result was nginx single at 27.7k rps.
3. Tako's built-in per-client-IP cap returns 429 above 2048 concurrent requests
   from one source IP. That is correct DDoS-protection behavior, but benchmarks
   above c2048 must either shard source IPs or apply an equivalent cap to nginx
   and Caddy.
4. Source-sharded Tako beats nginx on clean 200 rps at c2500 and c5000 in the
   VM-local test, but p99 latency is already high. That is overload behavior,
   not a good production target.
5. Tako's load-balanced path still underperforms Tako single-instance in the
   useful latency range. That makes load-balanced request selection and
   upstream handling the first area to profile.
6. Caddy 2.6.2 was much slower than both nginx and Tako in this setup.
7. Tako proxy RSS grows sharply at high concurrency, reaching about 730 MiB at
   c5000 and 1.4 GiB at c10000 in single-instance mode. Nginx uses much less
   proxy RSS in the same rows.
8. The channel/workflow feature path was blocked in the released server by the
   internal socket issue. The patched source build fixed the failure and
   produced clean 200-only results.
9. The laptop-driven benchmark is not a pure local proxy ceiling test. It
   includes a real 28-33ms Tailscale path from the laptop to Tokyo.

## Follow-up Profiling Targets

- Profile Tako load-balanced HTTP at `c=500` and higher:
  - upstream selection path
  - per-request locking in the route/load-balancer path
  - connection reuse and keep-alive behavior to app instances
  - health/state checks on hot request paths
- Profile memory growth in Tako under c2500-c10000:
  - TLS/session allocation behavior
  - Pingora request/session buffering
  - response body handling for very small responses
  - per-request metadata cloned into the proxy context
- Make the per-IP concurrent request cap configurable, or expose a benchmark
  mode that can raise it explicitly. Keep the current default for production
  DDoS protection.
- Add a second same-region load-generator VM. VM-local load generation is useful
  for total-box throughput, but it makes the client compete with the proxy and
  app for the same 2 vCPUs.
- Add repeated runs and confidence intervals after the first load-balanced Tako
  optimization pass.
- Keep channel/workflow benchmarks in CI or release validation so internal
  socket regressions fail before release.

## Reproducing

Prepare the VM from this repo:

```bash
BENCH_VM=<ssh-host> ./scripts/sync-to-vm.sh
```

Run HTTP proxy comparisons:

```bash
BENCH_VM=<ssh-host> BENCH_IP=<target-ip> CONCURRENCY_LIST="100 500" ./scripts/run-http-benchmarks.sh
```

Run VM-local high-load comparisons with source-IP sharding:

```bash
BENCH_VM=<ssh-host> \
SOURCE_IPS="127.0.0.2,127.0.0.3,127.0.0.4,127.0.0.5,127.0.0.6,127.0.0.7,127.0.0.8,127.0.0.9,127.0.0.10,127.0.0.11,127.0.0.12,127.0.0.13,127.0.0.14,127.0.0.15,127.0.0.16,127.0.0.17" \
CONCURRENCY_LIST="100 500 1000 2500 5000 10000" \
WARMUP=5s \
DURATION=20s \
ENDPOINTS=plaintext \
./scripts/run-vm-local-http-benchmarks.sh
```

Render CPU/RAM graphs:

```bash
./scripts/render-metrics-graphs.sh results/<timestamp>/http-vm-local
```

Run Tako channel/workflow feature benchmarks with a patched server binary on
the VM:

```bash
BENCH_VM=<ssh-host> BENCH_IP=<target-ip> TAKO_SERVER_BIN=/opt/tako-performance/bin/tako-server-patched ./scripts/run-tako-feature-benchmarks.sh
```

Stop benchmark services:

```bash
ssh <ssh-host> 'cd /opt/tako-performance/source && ./scripts/remote/control.sh stop'
```

The sanitized environment summary is in `results/baseline-001/env/summary.md`.
