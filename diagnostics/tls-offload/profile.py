#!/usr/bin/env python3
"""Server-only exploratory profile; keep perf.data and decoded stacks private.

Run inside the benchmark container with linux-perf installed, after the original
installer setup. The two cases deliberately differ in background workload and
are attribution evidence, not performance acceptance measurements.
"""
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys

spec = importlib.util.spec_from_file_location('bench', '/perf/diagnostics/buffer-lifetime/run.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
original_start = bench.start_proxy
original_stop = bench.base.stop
state = {}


def start(variant, directory, sequence):
    server, upstream = original_start(variant, directory, sequence)
    trace = (directory / 'perf-record.log').open('wb')
    profiler = subprocess.Popen(
        ['perf', 'record', '-e', 'cpu-clock', '-F', '99', '--call-graph', 'dwarf,8192',
         '-p', str(server.pid), '-o', str(directory / 'perf.data')], stdout=trace, stderr=trace)
    state.update(server=server, profiler=profiler, directory=directory, trace=trace)
    if sequence == 2:
        bench.base.ready(server)
        state['background'] = bench.base.start(
            ['/build/buffer-load', '-workload', 'small', '-protocol', 'h1', '-workers', '16',
             '-duration', '18s', '-warmup', '0s', '-churn'], directory / 'background.json',
            env={**os.environ, 'GOMAXPROCS': '2'})
    return server, upstream


def stop(process):
    if process is not None and process is state.get('server'):
        background = state.get('background')
        if background is not None:
            background.wait(timeout=35)
        profiler = state['profiler']
        profiler.send_signal(signal.SIGINT)
        profiler.wait(timeout=10)
        state['trace'].close()
        for children in (False, True):
            name = 'perf-children.txt' if children else 'perf-self.txt'
            with (state['directory'] / name).open('w') as output:
                subprocess.run(
                    ['perf', 'report', '--stdio', '--children' if children else '--no-children',
                     '--percent-limit', '1', '--sort', 'dso,symbol', '--call-graph', 'none',
                     '-i', str(state['directory'] / 'perf.data')],
                    stdout=output, stderr=subprocess.DEVNULL, check=True)
    original_stop(process)


bench.start_proxy = start
bench.base.stop = stop
sys.argv = ['profile', '--scenarios', 'rate', '--variants', 'baseline', '--repetitions', '2']
bench.main()
