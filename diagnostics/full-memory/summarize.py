#!/usr/bin/env python3
"""Render measured cases without treating partial or failed runs as valid wins."""
import collections
import json
from pathlib import Path
import statistics
import sys


def render(root):
    results = json.loads((root / 'summary.json').read_text())
    groups = collections.defaultdict(list)
    for result in results:
        groups[result['concurrency'], result['variant']].append(result)
    held_mode = all(r.get('mode') == 'held' for r in results)
    label = 'Held PSS' if held_mode else 'Peak PSS'
    lines = [f'| Workers | Variant | Runs | {label}, MiB (mean; range) | RPS (mean) | Failed cases |',
             '| ---: | --- | ---: | ---: | ---: | ---: |']
    order = {'tako-64': 0, 'tako-32': 1, 'tako-16': 2, 'caddy': 3}
    for (workers, variant), cases in sorted(groups.items(), key=lambda item: (item[0][0], order[item[0][1]])):
        pss = [(c['held_pss_kib'] if held_mode else c['peak']['pss_kib']) / 1024 for c in cases]
        rps = statistics.mean(c['load']['requests_per_sec'] for c in cases)
        failures = sum(not c['success'] for c in cases)
        lines.append(f'| {workers:,} | {variant} | {len(cases)} | '
                     f'{statistics.mean(pss):.1f}; {min(pss):.1f}–{max(pss):.1f} | {"—" if held_mode else f"{rps:,.0f}"} | {failures} |')
    lines += ['', 'Held PSS is the median while all exercised connections stay open; active PSS is the sampled peak including warmup and churn.',
              'RPS includes request draining after the nominal duration. Read errors and latency in the raw JSON.',
              'Compare successful cases with the same worker count; missing repetitions remain incomplete.']
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    print(render(Path(sys.argv[1])), end='')
