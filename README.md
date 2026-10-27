# Tako Performance

Complete, reproducible comparisons of Tako, nginx, HAProxy, Envoy and Caddy.

The current [27 October full-suite report](results/20261027-full-suite/README.md)
contains all 135 cases, throughput, latency, errors, CPU, memory, channels and
workflows. [RESULTS.md](RESULTS.md) summarizes the findings and measurement limits.
Every chart uses this dataset; older VM results remain in the
[archive](results/archived-vm-summary.md).

## Run in GitHub Actions

Use the free standard Ubuntu runner and the pinned
[full-suite workflow](.github/workflows/full-suite.yml). Each repetition compares
all five proxies in a two-CPU, 8 GiB, no-swap container. Proxy, app and load
generator share that budget. Read the [harness guide](diagnostics/full-suite/README.md)
for source pins, matched backend limits, checks and artifact contents.

```bash
gh workflow run full-suite.yml -R tako-sh/performance --ref '<performance-branch>'
gh run list -R tako-sh/performance --branch '<performance-branch>'
gh run watch '<run-id>' -R tako-sh/performance --exit-status
gh run download '<run-id>' -R tako-sh/performance --dir '<artifact-directory>'
```

Manual dispatch requires the workflow to exist on the default branch. Before
that, use its PR-triggered run. Verify the run's exact source and harness revisions.
Do not compare a narrow experiment with historical charts as a full refresh.

To regenerate the current report after collecting its artifacts:

```bash
python3 results/20261027-full-suite/analyze.py results/20261027-full-suite
python3 results/20261027-full-suite/render.py results/20261027-full-suite
```

The dated analyzer checks all identities and raw metrics, preserves the three
recorded sampling caveats, and marks the invalid CPU aggregate unavailable.
It does not edit the raw data. Rendering requires Matplotlib.

## Diagnostic and historical evidence

- [Merged buffer-lifetime validation](results/20261026-buffer-release/README.md):
  188 complete correctness cases, held/streaming memory and paired performance.
- [Initial buffer experiments](results/20261026-buffer-lifetime/README.md).
- [TLS offload investigation](results/20261026-tls-offload/README.md).
- [Memory harness](diagnostics/full-memory/README.md),
  [buffer harness](diagnostics/buffer-lifetime/README.md), and
  [production validation](diagnostics/release-validation/README.md).
- [Historical VM report](results/archived-vm-summary.md); remote scripts and proxy
  configs remain available for dedicated test machines.

Raw failures and superseded runs are retained. Public reports exclude credentials,
private hosts and runtime logs. Load-balanced mode requires a larger or multi-node
testbed and is outside this single-host suite.
