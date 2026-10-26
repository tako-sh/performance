#!/usr/bin/env python3
"""Reuse the full-server harness with optional longer traffic measurements."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--duration', type=int)
options, remaining = parser.parse_known_args()
if options.duration is not None and options.duration < 1:
    parser.error('duration must be positive')

spec = importlib.util.spec_from_file_location('buffers', '/perf/diagnostics/buffer-lifetime/run.py')
buffers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(buffers)
if options.duration is not None:
    for scenario in buffers.SCENARIOS.values():
        if scenario['mode'] not in ('held', 'stream'):
            scenario['duration'] = options.duration

Path('/results/validation.json').write_text(json.dumps({
    'duration_override_seconds': options.duration,
    'wrapper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
}, indent=2) + '\n')
sys.argv = [sys.argv[0], *remaining]
buffers.main()
