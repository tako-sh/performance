# Validate the production buffer release

The [workflow](../../.github/workflows/buffer-release.yml) compares a separately
built unchanged master with the production candidate in Tako PR #164. Both builds
use the same checkout path, pinned compiler and dependency lockfile; only the
Pingora core path override differs. No benchmark patch or runtime flag controls
the candidate. It always uses the new buffer lifetime behavior. The existing
`combined` result label identifies that binary in the reused harness.

Run all memory, HTTP/1 and HTTP/2 scenarios with baseline, combined and Caddy,
three repetitions each, reversing order on alternate repetitions. Expected case
counts are 18 memory, 54 HTTP/1 and 36 HTTP/2. The extra `small-repeat` job runs
eight paired baseline/combined repeats with 60-second measurement windows (16
cases), keeping the three-second warmup and sampler barrier. It targets the
small-response difference seen in the earlier switched prototype.

All groups reuse the original installer, deployed Go fixture, private container
namespaces, 2 CPU quota, 8 GiB RAM, no swap and corrected unique-socket counter.
They run on free standard GitHub runners. See the [buffer harness guide](../buffer-lifetime/README.md)
for correctness checks, memory/CPU boundaries and interpretation. Separate jobs
are separate hosts; compare each candidate with its control in the same job.

The wrapper changes only traffic duration when requested and records its hash
and override in `validation.json`. Per-case settings record the effective
duration too. The build manifest pins baseline and candidate revisions and hashes
the actual binaries. Results are `buffer-release-<group>-<sha>` artifacts, retained
for 14 days; runtime logs are excluded. Inspect expected counts, all success
flags, paired RPS/CPU/p95/p99 and every failed or incomplete case before publishing.

Use the PR trigger until this workflow exists on the default branch. Afterward,
dispatch `buffer-release.yml` on the intended pinned ref. Summary command:

```bash
python3 diagnostics/buffer-lifetime/summarize.py <downloaded-group-directory>
```

Keep historical five-proxy VM measurements separate from these runner results.
Publish matched current-control/candidate/Caddy results with the source identity
and limitations; do not substitute a held-memory number for active saturation
memory or imply improvements in workloads where Caddy already leads.
