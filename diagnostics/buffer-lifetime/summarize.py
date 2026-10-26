#!/usr/bin/env python3
"""Report all variants, preserving failed and missing repetitions."""
import collections
import json
from pathlib import Path
import statistics
import sys

def render(root):
    records=json.loads((root/'summary.json').read_text())
    groups=collections.defaultdict(list)
    for record in records:
        groups[record['workload'],record['variant']].append(record)
    lines=['| Workload | Variant | Runs / failed | Median-phase PSS MiB (mean) | Successful RPS (mean) | p99 ms (mean) | CPU µs/success (mean) |',
           '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for (workload,variant),cases in sorted(groups.items()):
        def mean(field,scale=1):
            values=[]
            for case in cases:
                value=case
                for key in field.split('.'):
                    value=value.get(key) if isinstance(value,dict) else None
                if value is not None: values.append(value*scale)
            return f'{statistics.mean(values):,.2f}' if len(values)==len(cases) else 'incomplete'
        rps='—' if workload in ('held','stream') else mean('load.requests_per_second')
        p99='—' if workload in ('held','stream') else mean('load.latency_ms.p99')
        cpu='—' if workload in ('held','stream') else mean('cpu_microseconds_per_success')
        lines.append(f"| {workload} | {variant} | {len(cases)} / {sum(not c['success'] for c in cases)} | {mean('phase_median_pss_kib',1/1024)} | {rps} | {p99} | {cpu} |")
    lines += ['', 'These are diagnostic paired experiments on shared CPU quota. Failed or incomplete cases are not performance wins.',
              'Memory is median process PSS during measurement/holding; inspect peak PSS and every repetition in raw JSON.',
              'CPU covers acknowledged measurement start through request drain. Compare latency at matched offered load, not only saturation.']
    return '\n'.join(lines)+'\n'

if __name__=='__main__':
    print(render(Path(sys.argv[1])),end='')
