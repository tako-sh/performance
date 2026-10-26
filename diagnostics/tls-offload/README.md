# TLS handshake offloading investigation

Pingora 0.9 offers `TlsSettings::set_offload_threadpool(shards, threads)`.
It moves downstream TLS handshakes onto a separate runtime. This can protect
established requests from expensive handshake work, but adds threads, scheduling
and memory. It does not make the cryptographic work disappear. Production Tako
defaults remain unchanged; this is a separate candidate from buffer reclamation.

The [measured report](../../results/20261026-tls-offload/README.md) records the
latency benefit, handshake throughput cost and overload limits.

## Why test it

A local server-only CPU profile provided a reason to investigate. Under a shared
2 CPU, 8 GiB, no-swap limit, a stream of 1,000 established HTTP/1 requests/s had
p99 1.42 ms without competing connections. With a separate 16-worker client
opening TLS connections for each request, its p99 rose to 47.21 ms. Both streams
completed without errors; the background achieved approximately 2,337 requests/s.
`perf record -e cpu-clock -F 99 --call-graph dwarf,8192 -p <server-pid>` showed
21.38% inclusive samples in OpenSSL `EVP_DigestSignFinal` and 18.38% in
`BN_mod_exp_mont_consttime_x2`. These inclusive percentages overlap.

This is one profiled observation, not proof of a particular offload configuration
or a performance acceptance result. Shared CPU quota and load-generator work also
contribute to latency. Profiles include warmup and setup, and symbol resolution
is incomplete. Raw stacks may contain machine paths and addresses and must stay
private; publish only reviewed aggregates. Offload acceptance runs omit perf.

`profile.py` reproduces the two exploratory cases using the existing container
fixtures. Install `linux-perf` in a disposable image and substitute this program
for the final Python command in `diagnostics/full-memory/entrypoint.sh`, keeping
the original installer, mounts and resource limits. It writes private perf data
and decoded reports alongside request JSON. Never upload those files wholesale.

## Controlled comparison

The [Actions workflow](../../.github/workflows/tls.yml) uses a free standard
Ubuntu runner and the same original installer, proxy configuration, app, RSA
certificate, pinned Tako revision and 2 CPU/8 GiB/no-swap container as the
[buffer investigation](../buffer-lifetime/README.md). Build the unchanged Tako
binary first, then apply `tako-tls.patch` and build a separate candidate. No
Pingora buffer patch is applied. Test Tako's proxy suite and the load fixtures.

Variants are unchanged Tako, one offload shard with one thread, one shard with
two threads, and pinned Caddy. The patch sets an experimental environment switch
on ordinary TLS listeners; it does not propose a new user-facing setting.

For each variant, keep foreground arrivals at 1,000 requests/s on reused TLS
connections. Add background arrivals at 0, 1,500 or 2,500 new TLS connections/s.
After foreground warmup, the sampler acknowledges both client barriers together.
Measure 15 seconds, four repetitions, reversing variant order every other run.
All variants receive the same scheduled arrivals. Latency includes queue delay;
the client drains every arrival rather than discarding excess work. Verify the
background's completed throughput, duration, errors and handshake count: a
lower foreground tail achieved by doing less background work is not a win.

Report foreground p95/p99, background completion rate, process PSS, thread count
and server CPU per **total foreground plus background request**. The clients and
app share the CPU quota with the proxy; these are controlled system experiments,
not estimates of dedicated proxy capacity. Certificate/key types and session
resumption alter the result; this client does not enable a TLS session cache.
This focused test does not establish peak-throughput or HTTP/2 acceptance.

## Run and inspect

Before the workflow reaches the default branch, use its PR trigger. Afterward:

```bash
gh workflow run tls.yml -R tako-sh/performance --ref <branch>
python3 diagnostics/tls-offload/summarize.py <downloaded-results-directory>
```

Select and download the exact run using Tako's `commands/performance.md`.
Artifacts `tls-results-<sha>` contain raw JSON and build hashes, retained for 14
days. They exclude runtime logs and profiler data. Check workflow completion and
every case's success flag before comparing results. A successful case validates
content, HTTP version, exact arrival count, and fresh background handshakes; it
does not imply the requested rate was sustainable.

For a local correctness check, use the workflow's container mounts and limits,
with `bash /perf/diagnostics/tls-offload/entrypoint.sh --smoke --repetitions 1`.
Use `--rates` and `--variants` for focused comparisons and include the baseline.

Keep production defaults and public headline tables unchanged until paired
measurements establish a useful latency benefit without throughput or CPU
regression and account for extra memory. Any final candidate must also retain
the required advantage over Caddy and pass broader transfer and HTTP/2 coverage.
