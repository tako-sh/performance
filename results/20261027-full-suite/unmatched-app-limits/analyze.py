#!/usr/bin/env python3
"""Validate all 135 cases and export the one dataset used by reports and website."""
import argparse
from collections import defaultdict
from datetime import datetime
import json
import math
from pathlib import Path
import statistics

PROXIES = ['nginx', 'haproxy', 'tako', 'envoy', 'caddy']
HTTP_LEVELS = [1000, 2500, 5000, 7500, 10000, 15000, 20000]
FEATURE_LEVELS = [500, 1000, 2000, 4000, 8000]
TAKO_REVISION = '1093899fd6b09d6227e5b7b585ee8bfeb4b5c028'


def close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-7), (actual, expected)


def mean_range(values):
    assert all(math.isfinite(x) for x in values)
    return dict(mean=statistics.mean(values), minimum=min(values), maximum=max(values), repetitions=values)


def analyze(root):
    groups, manifests, images, versions, binary_sets, cases = [], set(), set(), [], [], []
    for group in ['http', 'features']:
        for repetition in [1, 2, 3]:
            directory = root / f'{group}-{repetition}'
            metadata = json.loads((directory / 'metadata.json').read_text())
            args = metadata['arguments']
            assert args == dict(group=group, repetition=repetition, warmup=10, duration=30, cooldown=10), args
            assert metadata['cpu_max'] == '200000 100000'
            assert int(metadata['memory_max']) == 8 * 1024**3 and metadata['swap_max'] == '0'
            assert len(metadata['affinity']) == 2
            manifest = (directory / 'build.txt').read_text()
            assert f'tako_revision={TAKO_REVISION}' in manifest
            manifests.add(manifest)
            images.add((directory / 'runtime-image.txt').read_text().strip())
            versions.append(metadata['versions'])
            binary_sets.append((metadata['binaries'], metadata['proxy_binaries'], metadata['runner_sha256'], metadata['packages']))
            rows = json.loads((directory / 'summary.json').read_text())
            expected = {(p, 'plaintext', c) for p in PROXIES for c in HTTP_LEVELS} if group == 'http' else {
                ('tako', endpoint, c) for endpoint in ['channel-publish', 'workflow-enqueue'] for c in FEATURE_LEVELS}
            assert {(r['proxy'], r['endpoint'], r['concurrency']) for r in rows} == expected
            assert len(rows) == len(expected)
            for row in rows:
                assert row['repetition'] == repetition and row['completed'] is True
                case_dir = directory / row['name']
                assert json.loads((case_dir / 'summary.json').read_text()) == row
                result = json.loads((case_dir / 'load.json').read_text())
                assert result == row['load']
                assert result['concurrency'] == row['concurrency']
                assert result['request_timeout_sec'] == 60 and result['source_ip_count'] == 16
                assert result['duration_sec'] >= 30
                assert result['host_header'] == 'bench.test' and result['server_name'] == 'bench.test'
                assert result['method'] == ('GET' if group == 'http' else 'POST')
                assert sum(result['status_counts'].values()) == result['requests']
                assert sum(result.get('error_kinds', {}).values()) == result['errors']
                attempts = result['requests'] + result['errors']
                assert attempts > 0
                ok = result['status_counts'].get('200', 0)
                close(row['rps200'], ok / result['duration_sec'])
                close(row['success_pct'], ok / attempts * 100)
                close(row['non200_pct'], (result['requests'] - ok) / attempts * 100)
                close(row['client_error_pct'], result['errors'] / attempts * 100)
                assert row['clean'] == (ok == attempts)
                if row['endpoint'] == 'workflow-enqueue':
                    preflight = json.loads((case_dir / 'workflow-preflight.json').read_text())
                    assert preflight == dict(status='succeeded', last_error=None, ack_steps=1)
                    assert row['workflow_after_load']['ack_steps'] > 0
                if group == 'http' and row['clean']:
                    assert result['bytes'] == ok * 13
                samples = json.loads((case_dir / 'samples.json').read_text())
                start = datetime.fromisoformat(result['started_at'].replace('Z', '+00:00')).timestamp()
                measured = [s for s in samples if start <= s['timestamp'] <= start + result['duration_sec']]
                assert len(measured) == row['resources']['sample_count'] and len(measured) >= 25
                seconds = measured[-1]['timestamp'] - measured[0]['timestamp']
                for process in ['proxy', 'app', 'loadgen']:
                    resource = row['resources'][process]
                    close(resource['peak_pss_mib'], max(s[process]['pss_kib'] for s in measured) / 1024)
                    close(resource['median_pss_mib'], statistics.median(s[process]['pss_kib'] for s in measured) / 1024)
                    close(resource['peak_rss_mib'], max(s[process]['rss_kib'] for s in measured) / 1024)
                    close(resource['peak_private_mib'], max(s[process]['private_kib'] for s in measured) / 1024)
                    close(resource['cpu_pct'], (measured[-1][process]['cpu_seconds'] - measured[0][process]['cpu_seconds']) / seconds / 2 * 100)
                    assert resource['peak_pss_mib'] > 0 and resource['cpu_pct'] >= 0
                close(row['resources']['total_cpu_pct'], (measured[-1]['cpu_seconds'] - measured[0]['cpu_seconds']) / seconds / 2 * 100)
                cases.append(row)
            groups.append(dict(group=group, repetition=repetition, metadata=metadata))
    assert len(manifests) == len(images) == 1
    assert all(v == versions[0] for v in versions)
    assert all(b == binary_sets[0] for b in binary_sets)
    assert len(cases) == 135
    combined = defaultdict(list)
    for case in cases:
        combined[(case['proxy'], case['endpoint'], case['concurrency'])].append(case)
    rows = []
    for (proxy, endpoint, concurrency), repetitions in combined.items():
        assert len(repetitions) == 3
        repetitions.sort(key=lambda r: r['repetition'])
        metrics = {key: mean_range([r[key] for r in repetitions]) for key in ['rps200', 'success_pct', 'non200_pct', 'client_error_pct']}
        for key in ['p50', 'p95', 'p99']:
            metrics[key] = mean_range([r['load']['latency_ms'][key] for r in repetitions])
        for key, process, metric in [('memory', 'proxy', 'peak_pss_mib'), ('medianMemory', 'proxy', 'median_pss_mib'),
                                     ('privateMemory', 'proxy', 'peak_private_mib'), ('proxyCpu', 'proxy', 'cpu_pct'),
                                     ('appMemory', 'app', 'peak_pss_mib'), ('appCpu', 'app', 'cpu_pct'),
                                     ('loadgenCpu', 'loadgen', 'cpu_pct')]:
            metrics[key] = mean_range([r['resources'][process][metric] for r in repetitions])
        metrics['cpu'] = mean_range([r['resources']['total_cpu_pct'] for r in repetitions])
        aggregate = dict(proxy=proxy, endpoint=endpoint, conc=concurrency, clean=all(r['clean'] for r in repetitions),
                         requests=sum(r['load']['requests'] for r in repetitions),
                         clientErrors=sum(r['load']['errors'] for r in repetitions),
                         non200=sum(r['load']['requests'] - r['load']['status_counts'].get('200', 0) for r in repetitions),
                         metrics=metrics, rawCases=[r['name'] for r in repetitions])
        if endpoint == 'workflow-enqueue':
            aggregate['workflowAfterLoad'] = [r['workflow_after_load'] for r in repetitions]
        rows.append(aggregate)
    result = dict(resultDirectory=root.name, takoRevision=TAKO_REVISION, totalCases=135, repetitions=3,
                  date=max(r['load']['started_at'][:10] for r in cases),
                  versions=versions[0], runtimeImage=next(iter(images)),
                  hosts=[dict(group=g['group'], repetition=g['repetition'], cpu=g['metadata']['cpu_model'],
                              kernel=g['metadata']['kernel'], os=g['metadata']['os']['PRETTY_NAME']) for g in groups],
                  http=[r for r in rows if r['endpoint'] == 'plaintext'],
                  features=[r for r in rows if r['endpoint'] != 'plaintext'])
    (root / 'analysis.json').write_text(json.dumps(result, indent=2) + '\n')
    (root / 'website-data.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'Validated {len(cases)} cases: 105 HTTP, 30 feature; {sum(r["clean"] for r in cases)} clean cases.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    analyze(parser.parse_args().directory)
