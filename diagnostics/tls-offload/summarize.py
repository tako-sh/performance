#!/usr/bin/env python3
import collections
import json
from pathlib import Path
import statistics
import sys

def render(root):
    groups=collections.defaultdict(list)
    for r in json.loads((root/'summary.json').read_text()): groups[r['background_rate'],r['variant']].append(r)
    lines=['| TLS arrivals/s | Variant | Runs / failed | Foreground p95 / p99 ms | Background completed RPS | PSS MiB | Threads | CPU µs/total request |',
           '| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    def mean(cases,field,scale=1):
        values=[]
        for c in cases:
            for key in field.split('.'): c=c.get(key) if isinstance(c,dict) else None
            if c is not None: values.append(c*scale)
        return f'{statistics.mean(values):.2f}' if len(values)==len(cases) else 'incomplete'
    for (rate,variant),cases in sorted(groups.items()):
        bg=mean(cases,'background.requests_per_second') if rate else '—'
        lines.append(f"| {rate} | {variant} | {len(cases)} / {sum(not c['success'] for c in cases)} | {mean(cases,'primary.latency_ms.p95')} / {mean(cases,'primary.latency_ms.p99')} | {bg} | {mean(cases,'median_pss_kib',1/1024)} | {mean(cases,'threads')} | {mean(cases,'cpu_microseconds_per_total_request')} |")
    lines+=['','Foreground arrivals are fixed at 1,000 requests/s. Inspect background completion time and errors before claiming latency wins.',
            'CPU includes both streams; throughput and memory costs still matter. Profiling is performed separately from acceptance measurements.']
    return '\n'.join(lines)+'\n'
if __name__=='__main__': print(render(Path(sys.argv[1])),end='')
