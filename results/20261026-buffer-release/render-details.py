import json
from pathlib import Path
import statistics as s
import sys
root=Path(sys.argv[1])
lines=['# Complete production buffer comparisons', '', 'Each row is the mean of the listed repetitions. Memory is median holding/measuring-phase proxy PSS. Latency and CPU use the same measurement boundaries as the raw data; saturated latency is not a matched-load comparison.', '', '| Group | Workload | Variant | Valid cases | PSS MiB | RPS | p95 ms | p99 ms | CPU µs/success |', '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for group in ['memory','h1','h2','small-repeat','h2-download-repeat','h2-rate-repeat','chunked-repeat','chunked-rate-repeat']:
 path=root/('ci-'+group)/'summary.json'
 if not path.exists(): continue
 records=json.loads(path.read_text())
 for workload in dict.fromkeys(c['workload'] for c in records):
  for variant in ['baseline','combined','caddy']:
   cases=[c for c in records if c['workload']==workload and c['variant']==variant]
   if not cases: continue
   assert all(c['success'] for c in cases)
   memory=s.mean(c['phase_median_pss_kib']/1024 for c in cases)
   if workload in ('held','stream'):
    fields=['—']*4
   else:
    fields=[f"{s.mean(c['load']['requests_per_second'] for c in cases):,.2f}",*[f"{s.mean(c['load']['latency_ms'][q] for c in cases):,.3f}" for q in ['p95','p99']],f"{s.mean(c['cpu_microseconds_per_success'] for c in cases):,.2f}"]
   lines.append(f"| {group} | {workload} | {variant} | {len(cases)}/{len(cases)} | {memory:,.2f} | {' | '.join(fields)} |")
(root/'details.md').write_text('\n'.join(lines).rstrip()+'\n')
lines=['# Longer paired measurements', '', 'All measurements are 60 seconds after three seconds of warmup. Order alternates between baseline/candidate and candidate/baseline. No repetitions are excluded. Different groups use different runner hosts.', '']
for group in ['small-repeat','h2-download-repeat','h2-rate-repeat','chunked-repeat','chunked-rate-repeat']:
 path=root/('ci-'+group)/'summary.json'
 if not path.exists(): continue
 records=json.loads(path.read_text())
 lines += ['## '+group,'','| Pair | Baseline RPS | Candidate RPS | Change | Baseline CPU µs | Candidate CPU µs | Baseline p95 ms | Candidate p95 ms | Baseline p99 ms | Candidate p99 ms |','| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
 for rep in range(1,9):
  b=next(c for c in records if c['repetition']==rep and c['variant']=='baseline')
  c=next(c for c in records if c['repetition']==rep and c['variant']=='combined')
  br=b['load']['requests_per_second']; cr=c['load']['requests_per_second']
  fields=[str(rep),f'{br:,.2f}',f'{cr:,.2f}',f'{100*(cr/br-1):+.2f}%',f"{b['cpu_microseconds_per_success']:.2f}",f"{c['cpu_microseconds_per_success']:.2f}",*[f"{case['load']['latency_ms'][q]:.3f}" for q in ['p95','p99'] for case in [b,c]]]
  lines.append('| '+' | '.join(fields)+' |')
 lines += ['']
(root/'paired-details.md').write_text('\n'.join(lines).rstrip()+'\n')
