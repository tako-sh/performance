"""Focused sampler regressions; no benchmark container or load is required."""
import copy
import importlib.util
import os
import json
import sys
import tempfile
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
spec = importlib.util.spec_from_file_location('suite_runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(spec)
# Also permits running the exact tests against the original container-only loader.
original_spec = importlib.util.spec_from_file_location
with patch.object(importlib.util, 'spec_from_file_location', side_effect=lambda name, path: original_spec(
        name, Path(__file__).resolve().parents[1] / 'full-memory/run.py' if str(path) == '/perf/diagnostics/full-memory/run.py' else path)):
    spec.loader.exec_module(runner)

analyzer_spec = importlib.util.spec_from_file_location('suite_analyzer', Path(__file__).with_name('analyze.py'))
analyzer = importlib.util.module_from_spec(analyzer_spec)
analyzer_spec.loader.exec_module(analyzer)

RESULT = dict(started_at='1970-01-01T00:01:40Z', duration_sec=10)


def observation(timestamp, cpu):
    metrics = dict(pss_kib=2048, rss_kib=4096, private_kib=1024, cpu_seconds=cpu)
    return dict(timestamp=timestamp, cpu_seconds=cpu * 2, app_nofile=[[65535, 65535]],
                **{group: copy.deepcopy(metrics) for group in ['proxy', 'app', 'loadgen']})


class SamplerTests(unittest.TestCase):
    def test_unreaped_exit_is_not_zero_cpu(self):
        child = subprocess.Popen(['true'])
        try:
            # Wait for exit without reaping: /proc/PID/stat remains, smaps does not.
            os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOWAIT)
            with self.assertRaises(RuntimeError):
                runner.process_metrics({child.pid})
        finally:
            child.wait()

    def test_partial_group_read_is_not_a_partial_total(self):
        stat = '1 (worker) ' + ' '.join(['0'] * 20)
        metrics = dict(pss_kib=2048, rss_kib=4096, private_kib=1024, cpu_seconds=9)
        with patch.object(runner.Path, 'read_text', return_value=stat), \
                patch.object(runner.common, 'memory', side_effect=[metrics, PermissionError('unreadable')]):
            with self.assertRaises(RuntimeError):
                runner.process_metrics({1, 2})

    def test_empty_group_is_not_zero_cpu(self):
        with self.assertRaises(RuntimeError):
            runner.process_metrics(set())

    def test_live_process_is_measured(self):
        result = runner.process_metrics({os.getpid()})
        self.assertGreater(result['pss_kib'], 0)
        self.assertGreaterEqual(result['cpu_seconds'], 0)

    def test_unavailable_collection_is_recorded_for_live_or_exited_load(self):
        for error in [runner.IncompleteSample('exited'), ProcessLookupError('exited')]:
            for status in [None, 0]:
                with self.subTest(error=error, status=status), patch.object(runner, 'sample', side_effect=error):
                    sample = runner.collect_sample(Mock(), Mock(), Mock(poll=Mock(return_value=status)))
                    self.assertFalse(sample['valid'])
                    self.assertIn('exited', sample['unavailable_reason'])
                    self.assertNotIn('loadgen', sample)

    def test_exit_after_successful_reads_is_unavailable(self):
        with patch.object(runner, 'sample', side_effect=lambda *args: {'timestamp': 105}):
            sample = runner.collect_sample(Mock(), Mock(), Mock(poll=Mock(return_value=0)))
            self.assertFalse(sample['valid'])
            self.assertEqual(runner.collect_sample(Mock(), Mock(), Mock(poll=Mock(return_value=None))), {'timestamp': 105})

    def test_natural_child_exit_during_collection_preserves_case(self):
        child = subprocess.Popen(['true'])
        try:
            os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOWAIT)
            def collect(*args):
                # Discovery found this child before its natural exit. The load
                # generator remains alive when its /proc files are collected.
                runner.process_metrics({child.pid})
            with patch.object(runner, 'sample', side_effect=collect), \
                    patch.object(runner.time, 'time', side_effect=[102, 103]):
                unavailable = runner.collect_sample(Mock(), Mock(), Mock(poll=Mock(return_value=None)))
            samples = [observation(101, 1), unavailable, observation(105, 3)]
            original = copy.deepcopy(samples)
            summary = runner.summarize_samples(samples, RESULT)
            self.assertEqual(summary['sample_count'], 2)
            self.assertEqual(summary['loadgen']['cpu_pct'], 25)
            self.assertEqual(samples, original)
        finally:
            child.wait()

    def test_collection_continues_and_persists_unavailable_observation(self):
        samples = [observation(101, 1), dict(timestamp=103, valid=False, unavailable_reason='worker exited'), observation(105, 3)]
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(runner, 'collect_sample', side_effect=samples), \
                patch.object(runner.time, 'sleep'), \
                patch.object(runner.common, 'established_connections', return_value=5):
            actual = runner.collect_samples(Mock(poll=Mock(return_value=None)), Mock(),
                Mock(poll=Mock(side_effect=[None, None, None, 0])),
                Mock(warmup=10, duration=30), Path(directory))
            self.assertEqual(actual, samples)
            self.assertEqual(json.loads((Path(directory) / 'samples.json').read_text()), samples)

    def test_earlier_samples_persist_even_on_unexpected_collection_failure(self):
        earlier = observation(101, 1)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(runner, 'collect_sample', side_effect=[earlier, ValueError('unexpected')]), \
                patch.object(runner.time, 'sleep'), \
                patch.object(runner.common, 'established_connections', return_value=5):
            with self.assertRaisesRegex(ValueError, 'unexpected'):
                runner.collect_samples(Mock(poll=Mock(return_value=None)), Mock(),
                    Mock(poll=Mock(return_value=None)), Mock(warmup=10, duration=30), Path(directory))
            self.assertEqual(json.loads((Path(directory) / 'samples.json').read_text()), [earlier])

    def test_timestamp_is_taken_after_all_metrics(self):
        clock = [100]
        def metrics(_):
            clock[0] += 1
            return dict(pss_kib=1, rss_kib=1, private_kib=1, cpu_seconds=1)
        with patch.object(runner, 'descendants', side_effect=lambda pid: {pid}), \
                patch.object(runner.resource, 'prlimit', return_value=(65535, 65535)), \
                patch.object(runner, 'process_metrics', side_effect=metrics), \
                patch.object(runner.Path, 'read_text', side_effect=['usage_usec 1000000', '123']), \
                patch.object(runner, 'cgroup_cpu', return_value=5), \
                patch.object(runner.time, 'time', side_effect=lambda: clock[0]):
            sample = runner.sample(Mock(pid=1), Mock(pid=2), Mock(pid=3))
        self.assertEqual(sample['timestamp'], 103)
        self.assertEqual(sample['collection_started_at'], 100)

    def test_valid_summary_keeps_zero_cpu_and_two_cpu_normalization(self):
        samples = [observation(101, 1), observation(103, 2), observation(105, 3)]
        for sample in samples:
            sample['app']['cpu_seconds'] = 4
        summary = runner.summarize_samples(samples, RESULT)
        self.assertEqual(summary['loadgen']['cpu_pct'], 25)
        self.assertEqual(summary['app']['cpu_pct'], 0)
        self.assertEqual(summary['total_cpu_pct'], 50)
        self.assertEqual(summary['proxy']['peak_pss_mib'], 2)

    def test_invalid_counters_are_rejected_including_interior_reset(self):
        for group in ['proxy', 'app', 'loadgen', None]:
            for value in [0, -1, float('nan'), float('inf')]:
                with self.subTest(group=group, value=value):
                    samples = [observation(101, 1), observation(103, 2), observation(105, 3)]
                    target = samples[1][group] if group else samples[1]
                    target['cpu_seconds'] = value
                    with self.assertRaises(RuntimeError):
                        runner.summarize_samples(samples, RESULT)

    def test_changed_process_set_rejected_even_when_counter_increases(self):
        samples = [observation(101, 1), observation(105, 3)]
        samples[0]['loadgen']['processes'] = [[42, '1']]
        samples[1]['loadgen']['processes'] = [[42, '2']]
        with self.assertRaises(RuntimeError):
            runner.summarize_samples(samples, RESULT)

    def test_duplicate_or_backwards_time_is_rejected(self):
        for times in [(101, 101), (105, 103, 106)]:
            with self.subTest(times=times), self.assertRaises(RuntimeError):
                runner.summarize_samples([observation(t, i) for i, t in enumerate(times)], RESULT)

    def test_entire_collection_must_fit_measurement_window(self):
        samples = [observation(101, 0), observation(103, 2), observation(105, 3), observation(111, 0)]
        samples[0]['collection_started_at'] = 99
        summary = runner.summarize_samples(samples, RESULT)
        self.assertEqual(summary['sample_count'], 2)
        self.assertEqual(summary['loadgen']['cpu_pct'], 25)


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.samples = [observation(t, t - 100) for t in range(101, 128)]
        self.result = {**RESULT, 'duration_sec': 30}
        self.resources = runner.summarize_samples(self.samples, self.result)

    def test_valid_and_explicitly_unavailable_samples(self):
        self.samples.insert(5, dict(timestamp=105.5, valid=False, unavailable_reason='worker exited'))
        analyzer.validate_resources(self.samples, self.result, self.resources)

    def test_interior_counter_reset(self):
        self.samples[5]['loadgen']['cpu_seconds'] = 0
        with self.assertRaisesRegex(RuntimeError, 'invalid cumulative CPU'):
            analyzer.validate_resources(self.samples, self.result, self.resources)

    def test_process_identity_change(self):
        for sample in self.samples:
            sample['loadgen']['processes'] = [[42, '1']]
        self.samples[5]['loadgen']['processes'] = [[42, '2']]
        with self.assertRaisesRegex(RuntimeError, 'process membership changed'):
            analyzer.validate_resources(self.samples, self.result, self.resources)

    def test_timestamp_order(self):
        self.samples[5]['timestamp'] = self.samples[4]['timestamp']
        with self.assertRaisesRegex(RuntimeError, 'timestamps must increase'):
            analyzer.validate_resources(self.samples, self.result, self.resources)

    def test_app_worker_turnover_uses_cgroup_cpu(self):
        for index, sample in enumerate(self.samples):
            sample['app']['processes'] = [[42 + index, '1']]
        analyzer.validate_resources(self.samples, self.result, self.resources)


if __name__ == '__main__':
    unittest.main()
