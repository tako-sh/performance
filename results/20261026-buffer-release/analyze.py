import collections
import hashlib
import json
import math
import re
from pathlib import Path
import statistics as s
import sys

root = Path(sys.argv[1])
expected = {'memory': 18, 'h1': 54, 'h2': 36, 'small-repeat': 16, 'h2-download-repeat': 16, 'h2-rate-repeat': 16, 'chunked-repeat': 16, 'chunked-rate-repeat': 16}
metrics = {
    'pss_mib': lambda c: c['phase_median_pss_kib'] / 1024,
    'rps': lambda c: c['load']['requests_per_second'],
    'cpu_us': lambda c: c['cpu_microseconds_per_success'],
    'p95_ms': lambda c: c['load']['latency_ms']['p95'],
    'p99_ms': lambda c: c['load']['latency_ms']['p99'],
}
all_hashes = []
runner_hashes = []
output = {}
for group, count in expected.items():
    path = root / ('ci-' + group)
    if not (path / 'summary.json').exists():
        raise FileNotFoundError(path / 'summary.json')
    records = json.loads((path / 'summary.json').read_text())
    metadata = json.loads((path / 'metadata.json').read_text())
    assert len(records) == count, (group, len(records), count)
    assert all(c['success'] and c['load']['errors'] == 0 for c in records), group
    assert metadata['cpu_max'] == '200000 100000'
    assert metadata['memory_max'] == '8589934592'
    assert metadata['swap_max'] == '0'
    assert hashlib.sha256((path / 'build.txt').read_bytes()).hexdigest() == metadata['binaries']['build.txt']
    all_hashes.append(metadata['binaries'])
    runner_hashes.append(metadata['runner_sha256'])
    manifest=(path / 'build.txt').read_text()
    assert 'baseline_revision=738e023e721cb6bfe63cda184b8e78ad7bf8d1c6' in manifest
    assert 'candidate_revision=35c4234595be4e66fc86339c2a37a298653a4c63' in manifest
    for digest, binary in re.findall(r'([0-9a-f]{64})  build/(\S+)', manifest):
        assert metadata['binaries'][binary] == digest, (group, binary)
    if group.endswith('-repeat'):
        assert all(c['settings']['duration'] == 60 and c['load']['duration_seconds'] >= 60 - (1 / c['settings']['rate'] if c['settings'].get('rate') else 0) for c in records)
    if group == 'chunked-rate-repeat':
        assert all(c['settings']['rate'] == 250 for c in records)
        assert all(c['load']['requests'] == 15000 and c['load']['requests_per_second'] >= 249 for c in records)

    groups = collections.defaultdict(dict)
    for c in records:
        for key in ('error_samples', 'errors'):
            assert not c['load'].get(key), (group, c['name'], key)
        if c['workload'] == 'held':
            assert c['held_connections'] and set(c['held_connections']) == {20000}
            assert c['load']['requests'] == 420000
        case_path = path / c['name']
        assert json.loads((case_path / 'summary.json').read_text()) == c
        assert json.loads((case_path / 'load.json').read_text()) == c['load']
        samples = json.loads((case_path / 'samples.json').read_text())
        phase = 'holding' if c['workload'] in ('held', 'stream') else 'measuring'
        selected = [sample for sample in samples if sample['phase'] == phase]
        assert selected
        assert s.median(sample['pss_kib'] for sample in (selected[4:] or selected)) == c['phase_median_pss_kib']
        assert max(sample['pss_kib'] for sample in samples) == c['peak_pss_kib']
        if c['workload'] not in ('held', 'stream'):
            cpu = c['measured_cpu_seconds'] * 1e6 / c['load']['requests']
            assert abs(cpu - c['cpu_microseconds_per_success']) < 1e-9

        cases = groups[c['workload']].setdefault(c['variant'], [])
        assert c['repetition'] not in [x['repetition'] for x in cases]
        cases.append(c)
    output[group] = {}
    print('\nGROUP', group, len(records), 'valid cases')
    for workload, variants in groups.items():
        result = {}
        for variant, cases in variants.items():
            cases.sort(key=lambda c: c['repetition'])
            assert len(cases) == (8 if group.endswith('-repeat') else 3)
            active = workload not in ('held', 'stream')
            result[variant] = {metric: s.mean(f(c) for c in cases) for metric, f in metrics.items() if active or metric == 'pss_mib'}
        paired = {}
        for metric, get in metrics.items():
            if workload in ('held', 'stream') and metric != 'pss_mib':
                continue
            changes = [100 * (get(c) / get(b) - 1) for b, c in zip(variants['baseline'], variants['combined'])]
            paired[metric] = changes
        result['paired_percent'] = paired
        output[group][workload] = result
        print(workload, json.dumps(result, sort_keys=True))
        if group.endswith('-repeat'):
            for metric, changes in paired.items():
                error = 2.364624251 * s.stdev(changes) / math.sqrt(len(changes))
                print('paired approximate t-interval', metric, s.mean(changes), (s.mean(changes)-error, s.mean(changes)+error))
assert len(set(runner_hashes)) == 1, 'different base harnesses'
assert all(h == all_hashes[0] for h in all_hashes), 'different measured binaries'
(root / 'analysis.json').write_text(json.dumps(output, indent=2) + '\n')
