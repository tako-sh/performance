#!/usr/bin/env python3
"""Five-proxy and Tako feature suite, only inside a disposable test container."""
import argparse
from datetime import datetime
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

spec = importlib.util.spec_from_file_location('common', '/perf/diagnostics/full-memory/run.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
OUT, DATA = common.OUT, common.DATA
ROOT = Path('/opt/tako-performance')
PROXIES = ['nginx', 'haproxy', 'tako', 'envoy', 'caddy']
LEVELS = [1000, 2500, 5000, 7500, 10000, 15000, 20000]
FEATURE_LEVELS = [500, 1000, 2000, 4000, 8000]
ENV = {**os.environ, 'GOMAXPROCS': '2'}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def descendants(pid):
    found = {pid}
    for _ in range(8):
        old = len(found)
        for stat in Path('/proc').glob('[0-9]*/stat'):
            try:
                fields = stat.read_text().rsplit(')', 1)[1].split()
                if int(fields[1]) in found:
                    found.add(int(stat.parent.name))
            except (OSError, ValueError):
                pass
        if len(found) == old:
            break
    return found


def app_pids():
    found = set()
    root = Path('/sys/fs/cgroup/tako-apps')
    if root.exists():
        for f in root.rglob('cgroup.procs'):
            try:
                found.update(map(int, f.read_text().split()))
            except OSError:
                pass
    return found


def process_metrics(pids):
    total = dict(pss_kib=0, rss_kib=0, private_kib=0, cpu_seconds=0)
    for pid in pids:
        try:
            for key, value in common.memory(pid).items():
                total[key] += value
        except (OSError, ProcessLookupError):
            pass
    return total


def cgroup_cpu():
    return int(dict(line.split() for line in Path('/sys/fs/cgroup/cpu.stat').read_text().splitlines())['usage_usec']) / 1e6


def sample(server, upstream, load):
    apps = app_pids() if upstream is None else descendants(upstream.pid)
    return dict(timestamp=time.time(), proxy=process_metrics(descendants(server.pid) - apps),
                app=process_metrics(apps), loadgen=process_metrics(descendants(load.pid)),
                cpu_seconds=cgroup_cpu(), memory_bytes=int(Path('/sys/fs/cgroup/memory.current').read_text()))


def prepare():
    common.prepare()
    for sub in ['certs', 'run', 'logs', 'nginx']:
        (ROOT / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy('/certs/cert.pem', ROOT / 'certs/bench.test.crt')
    shutil.copy('/certs/key.pem', ROOT / 'certs/bench.test.key')
    (ROOT / 'certs/bench.test.pem').write_bytes(Path('/certs/cert.pem').read_bytes() + Path('/certs/key.pem').read_bytes())
    (ROOT / 'certs/bench.test.pem').chmod(0o600)
    runtime = DATA / 'runtimes/bun/1.4.4'
    runtime.mkdir(parents=True, exist_ok=True)
    shutil.copy('/build/bun', runtime / 'bun')
    (runtime / 'bun').chmod(0o755)


def ready(server, endpoint):
    for _ in range(300):
        if server.poll() is not None:
            raise RuntimeError('proxy exited before readiness')
        r = subprocess.run(['curl', '--http1.1', '--silent', '--show-error', '--fail',
                            '--max-time', '5', '--cacert', '/certs/cert.pem', '--noproxy', '*',
                            '--resolve', 'bench.test:18443:127.0.0.1',
                            f'https://bench.test:18443/{endpoint}'], capture_output=True)
        if r.returncode == 0:
            if endpoint == 'plaintext' and r.stdout == b'hello, world\n':
                return
            if endpoint == 'status' and json.loads(r.stdout).get('ok') is True:
                return
        time.sleep(0.1)
    raise RuntimeError(f'readiness failed: {r.stderr!r} {r.stdout!r}')


def start_tako(case_dir, name, feature):
    Path(common.SOCKET).unlink(missing_ok=True)
    server = common.start(['/usr/local/bin/tako-server', '--data-dir', str(DATA), '--socket', common.SOCKET,
                           '--http-port', '18080', '--https-port', '18443', '--metrics-port', '0', '--no-acme'],
                          case_dir / 'server.log', env=ENV)
    try:
        for _ in range(300):
            if Path(common.SOCKET).exists():
                break
            if server.poll() is not None:
                raise RuntimeError('Tako exited before management socket readiness')
            time.sleep(0.1)
        app = 'bench-features/production' if feature else common.APP
        release = DATA / f'apps/{app}/releases/{name}'
        release.mkdir(parents=True)
        if feature:
            subprocess.run(['tar', '-xf', '/build/features.tar', '-C', str(release)], check=True)
            manifest = dict(protocol_version=0, runtime='bun', runtime_version='1.4.4',
                            main='index.ts', app_dir='src', idle_timeout=300,
                            env_vars={'TAKO_BUILD': name})
        else:
            shutil.copy('/build/benchapp', release / 'benchapp')
            manifest = dict(protocol_version=0, runtime='go', main='benchapp', start=['./benchapp'],
                            idle_timeout=300, env_vars={'TAKO_BUILD': name, 'GOMAXPROCS': '2'})
        write_json(release / 'app.json', manifest)
        common.command(dict(command='deploy', app=app, version=name, path=str(release),
                            routes=['bench.test'], source_ip='direct', secrets={}, storages={}))
        common.command(dict(command='scale', app=app, instances=1))
        return server
    except BaseException:
        common.stop(server)
        raise


def start_proxy(case_dir, proxy, port):
    configs = {'nginx': 'configs/nginx/single.conf', 'haproxy': 'configs/haproxy/single.cfg',
               'envoy': 'configs/envoy/single.yaml', 'caddy': 'configs/caddy/single.Caddyfile'}
    config = Path('/perf', configs[proxy]).read_text().replace('127.0.0.1:9101', f'127.0.0.1:{port}')
    config = config.replace('port_value: 9101', f'port_value: {port}')
    config = config.replace('worker_processes auto;', 'worker_processes 2;').replace('__THREADS__', '2')
    file = case_dir / ('Caddyfile' if proxy == 'caddy' else 'proxy.yaml' if proxy == 'envoy' else 'proxy.conf')
    file.write_text(config)
    commands = {
        'nginx': ['nginx', '-c', str(file), '-p', str(ROOT / 'nginx'), '-g', 'daemon off;'],
        'haproxy': ['haproxy', '-W', '-db', '-f', str(file)],
        'envoy': ['envoy', '-c', str(file), '--concurrency', '2', '--log-level', 'warn'],
        'caddy': ['/build/caddy', 'run', '--config', str(file), '--adapter', 'caddyfile'],
    }
    return common.start(commands[proxy], case_dir / 'server.log', env=ENV)


def summarize_samples(samples, result):
    start = datetime.fromisoformat(result['started_at'].replace('Z', '+00:00')).timestamp()
    # The original load generator records RFC3339 seconds; bounds have <1 s
    # uncertainty. Keep raw timestamps and explicitly report this limitation.
    measured = [s for s in samples if start <= s['timestamp'] <= start + result['duration_sec']]
    if len(measured) < 2:
        raise RuntimeError('insufficient measurement samples')
    first, last = measured[0], measured[-1]
    seconds = last['timestamp'] - first['timestamp']
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


def case(args, proxy, endpoint, concurrency, index):
    name = f'r{args.repetition}-{proxy}-{endpoint}-c{concurrency}'
    case_dir = OUT / name
    case_dir.mkdir()
    server = upstream = load = None
    feature = endpoint != 'plaintext'
    try:
        if proxy == 'tako':
            server = start_tako(case_dir, name, feature)
        else:
            port = 10000 + index
            upstream = common.start(['/build/benchapp'], case_dir / 'app.log', env={**ENV, 'PORT': str(port)})
            server = start_proxy(case_dir, proxy, port)
        ready(server, 'status' if feature else 'plaintext')
        # Validate the feature's actual operation before timed load begins.
        if feature:
            response = subprocess.check_output(['curl', '--http1.1', '--silent', '--fail', '--max-time', '30',
                '--cacert', '/certs/cert.pem', '--noproxy', '*', '--resolve', 'bench.test:18443:127.0.0.1',
                '-X', 'POST', '-H', 'Content-Type: application/json', '--data', 'ok',
                f'https://bench.test:18443/{endpoint}'])
            payload = json.loads(response)
            if payload.get('ok') is not True or not payload.get('id'):
                raise RuntimeError(f'feature correctness check failed: {payload}')
        argv = ['/build/loadgen', '-name', name, '-url', f'https://127.0.0.1:18443/{endpoint}',
                '-host', 'bench.test', '-sni', 'bench.test', '-insecure', '-source-ips', common.SOURCE_IPS,
                '-concurrency', str(concurrency), '-warmup', f'{args.warmup}s',
                '-duration', f'{args.duration}s', '-request-timeout', '60s']
        if feature:
            argv.extend(['-method', 'POST', '-body', 'ok', '-content-type', 'application/json'])
        with (case_dir / 'load.json').open('wb') as output, (case_dir / 'load.stderr').open('wb') as error:
            load = subprocess.Popen(argv, stdout=output, stderr=error, env=ENV)
        samples, started = [], time.monotonic()
        while load.poll() is None:
            if server.poll() is not None:
                raise RuntimeError('proxy exited under load')
            current = sample(server, upstream, load)
            if len(samples) % 5 == 0:
                current['established_tls_port_connections'] = common.established_connections()
            samples.append(current)
            if time.monotonic() - started > args.warmup + args.duration + 180:
                raise RuntimeError('load generator deadline exceeded')
            time.sleep(1)
        if load.returncode:
            raise RuntimeError(f'load generator exited {load.returncode}')
        result = json.loads((case_dir / 'load.json').read_text())
        if not result['requests'] or sum(result['status_counts'].values()) != result['requests']:
            raise RuntimeError('invalid load result counts')
        if not feature and result['errors'] == 0 and set(result['status_counts']) == {'200'}:
            if result['bytes'] != 13 * result['requests']:
                raise RuntimeError('plaintext payload length mismatch')
        attempts = result['requests'] + result['errors']
        ok = result['status_counts'].get('200', 0)
        row = dict(name=name, proxy=proxy, endpoint=endpoint, concurrency=concurrency, repetition=args.repetition,
                   load=result, resources=summarize_samples(samples, result),
                   rps200=ok / result['duration_sec'], success_pct=ok / attempts * 100,
                   non200_pct=(result['requests'] - ok) / attempts * 100,
                   client_error_pct=result['errors'] / attempts * 100,
                   clean=ok == attempts, completed=True)
        write_json(case_dir / 'samples.json', samples)
        write_json(case_dir / 'summary.json', row)
        print(json.dumps({k: row[k] for k in ['name', 'rps200', 'success_pct', 'clean']}), flush=True)
        return row
    finally:
        common.stop(load)
        if proxy == 'tako' and server is not None and server.poll() is None:
            try:
                common.command(dict(command='delete', app='bench-features/production' if feature else common.APP))
            except (OSError, RuntimeError):
                pass
        common.stop(server)
        common.stop(upstream)
        root = Path('/sys/fs/cgroup/tako-apps')
        if root.exists():
            for kill in root.rglob('cgroup.kill'):
                kill.write_text('1')
        # Remove this disposable container's per-case app state, so durable
        # channel/workflow history cannot carry into the next repetition.
        for app in ['bench-http', 'bench-features']:
            path = DATA / 'apps' / app
            if path.exists():
                shutil.rmtree(path)
        time.sleep(args.cooldown)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--group', choices=['http', 'features', 'smoke'], required=True)
    parser.add_argument('--repetition', type=int, default=1)
    parser.add_argument('--warmup', type=int, default=10)
    parser.add_argument('--duration', type=int, default=30)
    parser.add_argument('--cooldown', type=int, default=10)
    args = parser.parse_args()
    prepare()
    versions = {}
    for name, command in {'nginx': ['nginx', '-v'], 'haproxy': ['haproxy', '-v'], 'envoy': ['envoy', '--version'],
                           'tako': ['/build/tako-server', '--version'], 'caddy': ['/build/caddy', 'version'],
                           'bun': ['/build/bun', '--version'], 'openssl': ['openssl', 'version']}.items():
        versions[name] = subprocess.check_output(command, stderr=subprocess.STDOUT, text=True).strip()
    metadata = dict(arguments=vars(args), kernel=platform.release(), architecture=platform.machine(),
        os=platform.freedesktop_os_release(), cpu_model=next(line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),
        affinity=sorted(os.sched_getaffinity(0)), cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
        memory_max=Path('/sys/fs/cgroup/memory.max').read_text().strip(), swap_max=Path('/sys/fs/cgroup/memory.swap.max').read_text().strip(),
        versions=versions, binaries={p.name: hashlib.file_digest(p.open('rb'), 'sha256').hexdigest() for p in Path('/build').iterdir() if p.is_file()},
        proxy_binaries={name: hashlib.file_digest(Path(shutil.which(name)).open('rb'), 'sha256').hexdigest() for name in ['nginx', 'haproxy', 'envoy']},
        runner_sha256=hashlib.file_digest(Path(__file__).open('rb'), 'sha256').hexdigest())
    write_json(OUT / 'metadata.json', metadata)
    cases = []
    if args.group in ['http', 'smoke']:
        for level in LEVELS if args.group == 'http' else [10]:
            order = PROXIES[args.repetition - 1:] + PROXIES[:args.repetition - 1]
            if level in LEVELS and LEVELS.index(level) % 2:
                order = list(reversed(order))
            cases.extend((proxy, 'plaintext', level) for proxy in order)
    if args.group in ['features', 'smoke']:
        for level in FEATURE_LEVELS if args.group == 'features' else [10]:
            cases.extend(('tako', endpoint, level) for endpoint in ['channel-publish', 'workflow-enqueue'])
    results = []
    for index, (proxy, endpoint, concurrency) in enumerate(cases):
        results.append(case(args, proxy, endpoint, concurrency, index))
        write_json(OUT / 'summary.json', results)
    assert len(results) == len(cases)


if __name__ == '__main__':
    main()
