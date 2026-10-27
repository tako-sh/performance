#!/usr/bin/env python3
"""Render the full report and standalone figures from validated analysis.json."""
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(sys.argv[1])
data = json.loads((root / 'analysis.json').read_text())
for row in data['features']:
    values = [a+b for a,b in zip(row['metrics']['non200_pct']['repetitions'],row['metrics']['client_error_pct']['repetitions'])]
    row['metrics']['failure_pct'] = dict(mean=sum(values)/len(values),minimum=min(values),maximum=max(values))
labels = {'nginx': 'nginx', 'haproxy': 'HAProxy', 'tako': 'Tako', 'envoy': 'Envoy', 'caddy': 'Caddy', 'channel-publish': 'Channel publish', 'workflow-enqueue': 'Workflow enqueue'}
colors = {'nginx': '#54505f', 'haproxy': '#8b68b1', 'tako': '#228469', 'envoy': '#ae812c', 'caddy': '#c65d57', 'channel-publish': '#c65d57', 'workflow-enqueue': '#228469'}
order = ['nginx', 'haproxy', 'tako', 'envoy', 'caddy']
plt.rcParams.update({'svg.hashsalt': 'tako-full-suite', 'font.family': 'DejaVu Sans', 'font.size': 10})
(root / 'graphs').mkdir(exist_ok=True)
charts = [('http', 'rps200', 'HTTP 200 responses per second', 'Responses / second'),
          ('http', 'p99', 'p99 response-header latency', 'Milliseconds'),
          ('http', 'memory', 'Peak proxy memory during load', 'MiB PSS'),
          ('http', 'proxyCpu', 'Proxy CPU usage', '% of two-CPU budget'),
          ('http', 'non200_pct', 'Non-200 HTTP outcomes', '% of attempts'),
          ('http', 'client_error_pct', 'Client errors', '% of attempts'),
          ('features', 'rps200', 'Feature HTTP 200 responses per second', 'Responses / second'),
          ('features', 'p99', 'Feature p99 response-header latency', 'Milliseconds'),
          ('features', 'memory', 'Feature proxy memory', 'MiB PSS'),
          ('features', 'failure_pct', 'Feature non-200 responses and client errors', '% of attempts')]
for group, metric, title, unit in charts:
    fig, ax = plt.subplots(figsize=(10, 5.4), constrained_layout=True)
    series = order if group == 'http' else ['channel-publish', 'workflow-enqueue']
    for key in series:
        rows = sorted((r for r in data[group] if r['proxy' if group == 'http' else 'endpoint'] == key), key=lambda r: r['conc'])
        x = [r['conc'] for r in rows]
        y = [r['metrics'][metric]['mean'] for r in rows]
        ax.plot(x, y, marker='o', markersize=4, linewidth=2, color=colors[key], label=labels[key])
        ax.fill_between(x, [r['metrics'][metric]['minimum'] for r in rows], [r['metrics'][metric]['maximum'] for r in rows], color=colors[key], alpha=.10)
    ax.set(title=title, xlabel='Concurrent clients', ylabel=unit)
    ax.set_ylim(bottom=0)
    ax.grid(axis='y', alpha=.2)
    ax.legend(loc='best', fontsize=9, ncol=2)
    ax.text(0, -.19, 'Lines: means of three runs. Bands: observed min–max. Proxy, app, and loadgen share 2 CPUs / 8 GiB.', transform=ax.transAxes, fontsize=8)
    fig.savefig(root / 'graphs' / f'{group}-{metric}.svg', metadata={'Date': None})
    svg = root / 'graphs' / f'{group}-{metric}.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    plt.close(fig)

def n(value, digits=0):
    return 'unavailable' if value is None else f'{value:,.{digits}f}'
def find(proxy, conc):
    return next(r for r in data['http'] if r['proxy'] == proxy and r['conc'] == conc)
def mean(row, metric):
    return row['metrics'][metric]['mean']

tako5, tako20 = find('tako', 5000), find('tako', 20000)
tako = [r for r in data['http'] if r['proxy'] == 'tako']
errors, non200 = sum(r['clientErrors'] for r in tako), sum(r['non200'] for r in tako)
text = [f'# Complete five-proxy benchmark — {data["date"]}', '',
        'This replaces the current public benchmark with a complete rerun of Tako, nginx, HAProxy, Envoy, and Caddy, plus Tako channel and workflow workloads. All charts and resource figures below come from this suite; historical VM and targeted buffer measurements remain separate archives.', '',
        f'All **135 measurement cases** completed: 105 HTTP cases and 30 feature cases. Every point has three repetitions. Tako averaged **{n(mean(tako5,"rps200"))} complete 200 RPS at c5000** and **{n(mean(tako20,"rps200"))} at c20000**. Across its 21 HTTP cases, it recorded **{n(non200)} non-200 responses and {n(errors)} client errors**.', '',
        f'Tako’s mean peak proxy PSS at c20000 was **{n(mean(tako20,"memory"),1)} MiB**, measured during those same throughput runs. Compare memory with successful outcomes; rejecting or timing out requests is not equivalent served capacity.', '',
        'Tako was faster than Caddy at every tested concurrency, but nginx, HAProxy and Envoy had higher successful throughput. Tako and HAProxy were clean across all their HTTP cases. The other proxies had non-200 responses or client errors in at least one case. The remaining Tako memory footprint is substantial; this report does not call that problem solved.', '',
        '## Measurement quality', '',
        'All 135 runs are included; 122 completed without HTTP or client errors. Two nginx c15000 runs supplied 24 and 23 resource samples rather than the planned minimum 25 (covering 29.04 s and 28.17 s). Their memory peaks may be undersampled. One Tako c15000 load-generator CPU counter reset when the process exited: that aggregate is **unavailable**, not a negative CPU value or an average of only the other two runs. Proxy/app CPU, total cgroup CPU, requests and memory are independently checked. See `qualityFlags` in analysis.json and the unchanged raw samples.', '',
        '## Setup and build identity', '',
        f'- Tako server and JavaScript SDK source: `{data["takoRevision"]}`.',
        '- Free standard Ubuntu 24.04 GitHub runners; a shared Ubuntu 26.04 container image.',
        '- Two assigned logical CPUs, a 2-CPU quota, 8 GiB memory limit, and no swap. Client, proxy, app, and sampler share the budget.',
        '- Each HTTP repetition runs all five proxies and all seven concurrency levels on one host. Proxy order rotates between repetitions and reverses at alternating levels. Feature repetitions run on separate hosts.',
        '- Original HTTP/1.1-over-TLS workload: one Go plaintext app, one RSA certificate per repetition, Host/SNI `bench.test`, 16 loopback source IPs, a 10-second warmup, 30-second measurement, 60-second request timeout, and 10-second cooldown.',
        '- Backend apps and workflow workers use matching 65,535-file descriptor limits, checked in every sample. Tako’s production app default is 4,096; this benchmark configures a higher app limit without changing the server binary.',
        '- Fresh processes and app state per case. Same original proxy configurations, with workers fixed at two and a fresh upstream port per case to avoid previous runs’ TIME_WAIT sockets consuming its port budget.',
        '- RPS uses actual elapsed time including request drain. Latency ends at response headers; incomplete response bodies count only as client errors. Error requests do not contribute latency samples.',
        '- One-second process/cgroup sampling. PSS apportions shared pages. nginx includes master and workers. App/workflow workers and loadgen are separate. Kernel socket memory is excluded.',
        '- Values are means of per-run metrics, including means of each run’s p99 and peak PSS. They are not pooled latency percentiles. Figure bands show the observed min–max, not confidence intervals.',
        '- New hardware and software establish a fresh baseline. Differences from the old exe.dev VM cannot be attributed solely to the buffer optimization.', '',
        '| Software | Recorded version |', '| --- | --- |']
for key, value in data['versions'].items():
    value = next(line.strip() for line in value.splitlines() if line.strip()).replace('|', '\\|')
    text.append(f'| {labels.get(key,key)} | {value} |')
text += ['', '| Group | Repetition | CPU | Kernel |', '| --- | ---: | --- | --- |']
for host in data['hosts']:
    text.append(f'| {host["group"]} | {host["repetition"]} | {host["cpu"]} | {host["kernel"]} |')
text += ['', f'Runtime image identity: `{data["runtimeImage"]}`. Each group’s metadata includes package versions and binary hashes; `build.txt` records the actual performance checkout. See [provenance.json](provenance.json) for workflow runs and artifacts.', '', '## HTTPS results', '']
for group, metric, title, unit in charts:
    if group == 'http': text += [f'![{title}](graphs/{group}-{metric}.svg)', '']
text += ['| Proxy | Concurrency | 200 RPS | RPS range | p50 ms | p95 ms | p99 ms | Non-200 % | Client-error % |', '| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |']
for conc in sorted({r['conc'] for r in data['http']}):
    for proxy in order:
        row=find(proxy,conc); spread=row['metrics']['rps200']
        text.append(f'| {labels[proxy]} | {conc:,} | {n(mean(row,"rps200"))} | {n(spread["minimum"])}–{n(spread["maximum"])} | {n(mean(row,"p50"),1)} | {n(mean(row,"p95"),1)} | {n(mean(row,"p99"),1)} | {n(mean(row,"non200_pct"),3)} | {n(mean(row,"client_error_pct"),3)} |')
text += ['', '## Memory and CPU from the same runs', '', '| Proxy | Concurrency | Peak PSS MiB | PSS range | Private MiB | 200 % | Proxy CPU % | App CPU % | Loadgen CPU % | Total CPU % |', '| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for conc in sorted({r['conc'] for r in data['http']}):
    for proxy in order:
        row=find(proxy,conc); spread=row['metrics']['memory']
        text.append(f'| {labels[proxy]} | {conc:,} | {n(mean(row,"memory"),1)} | {n(spread["minimum"],1)}–{n(spread["maximum"],1)} | {n(mean(row,"privateMemory"),1)} | {n(mean(row,"success_pct"),3)} | {n(mean(row,"proxyCpu"),1)} | {n(mean(row,"appCpu"),1)} | {n(mean(row,"loadgenCpu"),1)} | {n(mean(row,"cpu"),1)} |')
text += ['', '## Channels and workflows', '', 'The original SDK app publishes one durable channel message or enqueues one `noop` workflow whose handler persists an `ack` step. A preflight workflow must succeed with that step before each timed enqueue run. This measures **HTTP enqueue acceptance, not workflow completion throughput**. Post-load workflow state counts are retained below and in every raw case.', '']
for group, metric, title, unit in charts:
    if group == 'features': text += [f'![{title}](graphs/{group}-{metric}.svg)', '']
text += ['| Operation | Concurrency | 200 RPS | RPS range | p50 ms | p99 ms | Non-200 % | Client-error % | Proxy PSS MiB | App/worker PSS MiB |', '| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for row in sorted(data['features'],key=lambda r:(r['conc'],r['endpoint'])):
    spread=row['metrics']['rps200']
    text.append(f'| {labels[row["endpoint"]]} | {row["conc"]:,} | {n(mean(row,"rps200"))} | {n(spread["minimum"])}–{n(spread["maximum"])} | {n(mean(row,"p50"),1)} | {n(mean(row,"p99"),1)} | {n(mean(row,"non200_pct"),3)} | {n(mean(row,"client_error_pct"),3)} | {n(mean(row,"memory"),1)} | {n(mean(row,"appMemory"),1)} |')
text += ['', 'Workflow state immediately after HTTP load (includes preflight and warmup tasks; pending work is not a completed-workflow rate):', '', '| Concurrency | Repetition | Succeeded | Pending | Running | Dead | Cancelled | Persisted ack steps |', '| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
for row in sorted(data['features'],key=lambda r:r['conc']):
    for i,state in enumerate(row.get('workflowAfterLoad',[]),1):
        counts=state['runs']
        text.append(f'| {row["conc"]:,} | {i} | '+ ' | '.join(n(counts.get(k,0)) for k in ['succeeded','pending','running','dead','cancelled'])+f' | {state["ack_steps"]:,} |')
text += ['', '## Inspect and reproduce', '',
         '- [HTTP repetition 1](http-1/), [2](http-2/), [3](http-3/).',
         '- [Feature repetition 1](features-1/), [2](features-2/), [3](features-3/).',
         '- [Validated aggregates](analysis.json), [website dataset](website-data.json), [run provenance](provenance.json).',
         '- [Workflow](../../.github/workflows/full-suite.yml) and [method guide](../../diagnostics/full-suite/README.md).',
         '- Revalidate and regenerate aggregates with `python3 analyze.py .`; regenerate this report/figures with `python3 render.py .` (Matplotlib).',
         '- The [initial unmatched-limit run](unmatched-app-limits/) is retained as rejected comparison evidence; it also exposed process CPU counter resets. Current charts use only the corrected, matched-limit runs.',
         '- All completed repetitions, errors, and unfavorable outcomes are retained. Setup failures/corrections are documented in provenance and are not performance measurements.',
         '- Public artifacts contain measurements and build identities. Private runtime logs, credentials, and certificate keys are excluded.', '']
(root/'README.md').write_text('\n'.join(text))
print(f'Rendered {len(charts)} figures and complete report.')
