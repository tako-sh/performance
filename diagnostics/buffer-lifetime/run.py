#!/usr/bin/env python3
"""Matched full-server controls for buffer lifetime; only run in the test container."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import time

spec = importlib.util.spec_from_file_location('full_memory', '/perf/diagnostics/full-memory/run.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
OUT = Path('/results')
VARIANTS = ('baseline', 'idle', 'body', 'combined', 'caddy')
SCENARIOS = {
    'held': dict(mode='held', workers=20000, duration=10, protocol='h1'),
    'stream': dict(mode='stream', workers=2000, duration=10, protocol='h1'),
    'small': dict(mode='small', workers=64, duration=15, protocol='h1'),
    'rate': dict(mode='small', workers=128, duration=15, protocol='h1', rate=1000),
    'upload': dict(mode='upload', workers=32, duration=15, protocol='h1'),
    'chunked': dict(mode='chunked', workers=32, duration=15, protocol='h1'),
    'download': dict(mode='download', workers=32, duration=15, protocol='h1'),
    'churn': dict(mode='small', workers=32, duration=15, protocol='h1', churn=True),
    'h2-small': dict(mode='small', workers=64, duration=15, protocol='h2'),
    'h2-rate': dict(mode='small', workers=128, duration=15, protocol='h2', rate=1000),
    'h2-upload': dict(mode='upload', workers=32, duration=15, protocol='h2'),
    'h2-download': dict(mode='download', workers=32, duration=15, protocol='h2'),
}
GROUPS = {'memory': ('held', 'stream'), 'h1': ('small', 'rate', 'upload', 'chunked', 'download', 'churn'),
          'h2': ('h2-small', 'h2-rate', 'h2-upload', 'h2-download')}


def start_proxy(variant, directory, sequence):
    env = {**os.environ, 'GOMAXPROCS': '2', 'TAKO_BENCH_L4_READ_BYTES': '65536',
           'TAKO_BENCH_IDLE_L4': str(int(variant in ('idle', 'combined'))),
           'TAKO_BENCH_RELEASE_BODY': str(int(variant in ('body', 'combined')))}
    if variant == 'caddy':
        port = str(9100 + sequence)
        config = directory / 'Caddyfile'
        config.write_text(Path('/Caddyfile').read_text().replace('127.0.0.1:9101', f'127.0.0.1:{port}'))
        upstream = base.start(['/build/benchapp'], directory / 'app.log', env={**env, 'PORT': port})
        try:
            server = base.start(['/build/caddy', 'run', '--config', str(config), '--adapter', 'caddyfile'], directory / 'server.log', env=env)
        except BaseException:
            base.stop(upstream)
            raise
        return server, upstream
    binary = '/build/tako-server' if variant == 'baseline' else '/build/tako-candidate'
    # Preserve the installed executable path and original app-provisioning policy.
    shutil.copyfile(binary, '/usr/local/bin/tako-server')
    Path('/usr/local/bin/tako-server').chmod(0o755)
    Path(base.SOCKET).unlink(missing_ok=True)
    server = base.start(['/usr/local/bin/tako-server', '--data-dir', str(base.DATA), '--socket', base.SOCKET,
                         '--http-port', '18080', '--https-port', '18443', '--metrics-port', '0', '--no-acme'],
                        directory / 'server.log', env=env)
    try:
        for _ in range(300):
            if Path(base.SOCKET).exists():
                break
            if server.poll() is not None:
                raise RuntimeError('Tako exited before management socket was ready')
            time.sleep(.1)
        release = base.DATA / f'apps/{base.APP}/releases/{directory.name}'
        release.mkdir(parents=True)
        shutil.copy('/build/benchapp', release / 'benchapp')
        (release / 'app.json').write_text(json.dumps(dict(protocol_version=0, runtime='go', main='benchapp', start=['./benchapp'],
            idle_timeout=300, env_vars={'TAKO_BUILD': directory.name, 'GOMAXPROCS': '2'})))
        base.command(dict(command='deploy', app=base.APP, version=directory.name, path=str(release),
            routes=['bench.test'], source_ip='direct', secrets={}, storages={}))
        base.command(dict(command='scale', app=base.APP, instances=1))
    except BaseException:
        base.stop(server)
        raise
    return server, None


def phase(path):
    try:
        return json.loads(path.read_text())['phase']
    except FileNotFoundError:
        return 'starting'


def case(args, variant, workload, repetition, sequence):
    config = dict(SCENARIOS[workload])
    if args.smoke:
        config.update(workers=20 if config['mode'] in ('held', 'stream') else 4, duration=2)
    name = f'r{repetition}-{variant}-{workload}'
    directory = OUT / name
    directory.mkdir()
    load = server = upstream = None
    try:
        server, upstream = start_proxy(variant, directory, sequence)
        base.ready(server)
        time.sleep(1)
        phase_file = directory / 'phase.json'
        if config['mode'] == 'held':
            argv = ['/build/hold-connections', '-concurrency', str(config['workers']), '-phase-file', str(phase_file)]
        else:
            argv = ['/build/buffer-load', '-workload', config['mode'], '-protocol', config['protocol'],
                    '-workers', str(config['workers']), '-duration', f"{config['duration']}s", '-warmup', '1s' if args.smoke else '3s',
                    '-rate', str(config.get('rate', 0)), '-phase-file', str(phase_file)]
            if config.get('churn'):
                argv.append('-churn')
        before = base.memory(server.pid)
        started = time.monotonic()
        load = base.start(argv, directory / 'load.json', env={**os.environ, 'GOMAXPROCS': '2'})
        samples = []
        measured_before = None
        while load.poll() is None:
            sample = base.memory(server.pid)
            state = phase(phase_file)
            if state == 'ready' and measured_before is None:
                measured_before = sample.copy()
                Path(str(phase_file)+'.start').write_text('start')
            try:
                stat = Path(f'/proc/{load.pid}/stat').read_text().rsplit(')', 1)[1].split()
                client_cpu = (int(stat[11])+int(stat[12])) / os.sysconf('SC_CLK_TCK')
            except FileNotFoundError:
                break
            sample.update(elapsed=time.monotonic()-started, phase=state, client_cpu_seconds=client_cpu)
            if len(samples) % 20 == 0:
                sample['connections'] = base.established_connections()
            samples.append(sample)
            if sample['elapsed'] > 600:
                raise RuntimeError('load client deadline exceeded')
            time.sleep(.25)
        load.wait()
        measured_after = base.memory(server.pid)
        result = json.loads((directory / 'load.json').read_text())
        success = load.returncode == 0 and result['requests'] > 0 and result['errors'] == 0
        selected_phase = 'holding' if config['mode'] in ('held', 'stream') else 'measuring'
        selected = [s for s in samples if s['phase'] == selected_phase]
        record = dict(name=name, variant=variant, workload=workload, repetition=repetition, settings=config,
                      success=success and bool(selected), baseline=before, load=result,
                      peak_pss_kib=max(s['pss_kib'] for s in samples), samples=len(samples))
        if measured_before is not None:
            record['measured_cpu_seconds'] = measured_after['cpu_seconds']-measured_before['cpu_seconds']
            successful = result['requests']-result['errors']
            if successful > 0:
                record['cpu_microseconds_per_success'] = record['measured_cpu_seconds']*1e6/successful
            if result.get('payload_bytes', 0) > 0:
                record['cpu_seconds_per_gib'] = record['measured_cpu_seconds']/(result['payload_bytes']/2**30)
        if selected:
            record['phase_median_pss_kib'] = statistics.median(s['pss_kib'] for s in selected[4:] or selected)
            record['phase_cpu_seconds'] = selected[-1]['cpu_seconds']-selected[0]['cpu_seconds']
            record['phase_client_cpu_seconds'] = selected[-1]['client_cpu_seconds']-selected[0]['client_cpu_seconds']
            record['phase_sample_seconds'] = selected[-1]['elapsed']-selected[0]['elapsed']
        if config['mode'] == 'held':
            counts = [s['connections'] for s in selected if 'connections' in s]
            record['held_connections'] = counts
            record['success'] = record['success'] and bool(counts) and all(n == config['workers'] for n in counts)
            record['success'] = record['success'] and result['bytes'] == 13 * result['requests'] and set(result['status_counts']) == {'200'}
        (directory / 'samples.json').write_text(json.dumps(samples, indent=2)+'\n')
        (directory / 'summary.json').write_text(json.dumps(record, indent=2)+'\n')
        print(json.dumps({k:record[k] for k in ('name', 'success', 'phase_median_pss_kib') if k in record}), flush=True)
        return record
    finally:
        base.stop(load)
        base.stop(server)
        base.stop(upstream)
        for kill in Path('/sys/fs/cgroup/tako-apps').glob('**/cgroup.kill'):
            kill.write_text('1')
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--group', choices=GROUPS, default='memory')
    parser.add_argument('--scenarios')
    parser.add_argument('--variants', default=','.join(VARIANTS))
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    variants = args.variants.split(',')
    workloads = args.scenarios.split(',') if args.scenarios else GROUPS[args.group]
    if not set(variants).issubset(VARIANTS) or not set(workloads).issubset(SCENARIOS):
        parser.error('unknown variant or workload')
    metadata = dict(arguments=vars(args), kernel=platform.release(), architecture=platform.machine(),
        cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip(), memory_max=Path('/sys/fs/cgroup/memory.max').read_text().strip(),
        swap_max=Path('/sys/fs/cgroup/memory.swap.max').read_text().strip(),
        network_limits={key:Path('/proc/sys/'+key.replace('.', '/')).read_text().strip() for key in ('net.ipv4.ip_local_port_range', 'net.ipv4.ip_local_reserved_ports', 'net.core.somaxconn', 'net.ipv4.tcp_max_syn_backlog')},
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        binaries={p.name:hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in Path('/build').iterdir() if p.is_file()})
    (OUT / 'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    base.prepare()
    records=[]
    for repetition in range(1,args.repetitions+1):
        for workload in workloads:
            for variant in variants if repetition % 2 else reversed(variants):
                try:
                    record=case(args,variant,workload,repetition,len(records)+1)
                except Exception as error:
                    # Do not expose runtime logs or machine paths in public artifacts.
                    record=dict(variant=variant,workload=workload,repetition=repetition,success=False,error_type=type(error).__name__)
                    print(json.dumps(record),flush=True)
                records.append(record)
                (OUT / 'summary.json').write_text(json.dumps(records,indent=2)+'\n')
    if not all(r['success'] for r in records):
        raise SystemExit('failed/incomplete buffer cases; inspect per-case diagnostics')

if __name__=='__main__':
    main()
