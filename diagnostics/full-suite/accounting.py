"""Resource accounting shared by collection and offline validation."""
from datetime import datetime
import math
import statistics


def summarize_samples(samples, result):
    start = datetime.fromisoformat(result['started_at'].replace('Z', '+00:00')).timestamp()
    measured = [s for s in samples if s.get('valid', True) and start <= s.get('collection_started_at', s['timestamp']) <= s['timestamp'] <= start + result['duration_sec']]
    if len(measured) < 2:
        raise RuntimeError('insufficient measurement samples')
    first, last = measured[0], measured[-1]
    seconds = last['timestamp'] - first['timestamp']
    if any(b['timestamp'] <= a['timestamp'] for a, b in zip(measured, measured[1:])):
        raise RuntimeError('measurement timestamps must increase')
    for group in ['proxy', 'app', 'loadgen', None]:
        counters = [s[group]['cpu_seconds'] if group else s['cpu_seconds'] for s in measured]
        if any(not math.isfinite(c) or c < 0 for c in counters) or any(b < a for a, b in zip(counters, counters[1:])):
            raise RuntimeError(f'invalid cumulative CPU counters: {group or "total"}')
        # App CPU comes from its cumulative cgroup, which survives worker exits.
        if group in ['proxy', 'loadgen'] and any(s[group].get('processes') != first[group].get('processes') for s in measured):
            raise RuntimeError(f'process membership changed: {group}')
    resources = {}
    for group in ['proxy', 'app', 'loadgen']:
        resources[group] = dict(
            peak_pss_mib=max(s[group]['pss_kib'] for s in measured) / 1024,
            median_pss_mib=statistics.median(s[group]['pss_kib'] for s in measured) / 1024,
            peak_rss_mib=max(s[group]['rss_kib'] for s in measured) / 1024,
            peak_private_mib=max(s[group]['private_kib'] for s in measured) / 1024,
            cpu_pct=(last[group]['cpu_seconds'] - first[group]['cpu_seconds']) / seconds / 2 * 100)
    resources['total_cpu_pct'] = (last['cpu_seconds'] - first['cpu_seconds']) / seconds / 2 * 100
    resources['sample_count'] = len(measured)
    return resources
