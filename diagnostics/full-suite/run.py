#!/usr/bin/env python3
"""Five-proxy and Tako feature suite, only inside a disposable test container."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import sqlite3
import subprocess
import time

from accounting import summarize_samples

spec = importlib.util.spec_from_file_location('common', Path(__file__).resolve().parents[1] / 'full-memory/run.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
OUT, DATA = common.OUT, common.DATA
ROOT = Path('/opt/tako-performance')
PROXIES = ['nginx', 'haproxy', 'tako', 'envoy', 'caddy']
LEVELS = [1000, 2500, 5000, 7500, 10000, 15000, 20000]
FEATURE_LEVELS = [500, 1000, 2000, 4000, 8000]
ENV = {**os.environ, 'GOMAXPROCS': '2'}
APP_NOFILE = 65535


def match_app_limits(upstream):
    pids = app_pids() if upstream is None else descendants(upstream.pid)
    limits = []
    for pid in sorted(pids):
        before = resource.prlimit(pid, resource.RLIMIT_NOFILE)
        resource.prlimit(pid, resource.RLIMIT_NOFILE, (APP_NOFILE, APP_NOFILE))
        after = resource.prlimit(pid, resource.RLIMIT_NOFILE)
        limits.append(dict(before=list(before), after=list(after)))
    if not limits:
        raise RuntimeError('no backend app processes found')
    return limits


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


class IncompleteSample(RuntimeError):
    """A process disappeared or could not be read; its counters are not zero."""


def process_metrics(pids):
    if not pids:
        raise IncompleteSample('empty process group')
    total = dict(pss_kib=0, rss_kib=0, private_kib=0, cpu_seconds=0)
    identities = []
    for pid in sorted(pids):
        try:
            stat = Path(f'/proc/{pid}/stat')
            before = stat.read_text().rsplit(')', 1)[1].split()[19]
            metrics = common.memory(pid)
            after = stat.read_text().rsplit(')', 1)[1].split()[19]
            if before != after:
                raise IncompleteSample(f'process {pid} was replaced during collection')
            for key, value in metrics.items():
                total[key] += value
            identities.append([pid, before])
        except (OSError, KeyError, ValueError, IndexError) as error:
            raise IncompleteSample(f'cannot collect process {pid}') from error
    total['processes'] = identities
    return total


def cgroup_cpu():
    return int(dict(line.split() for line in Path('/sys/fs/cgroup/cpu.stat').read_text().splitlines())['usage_usec']) / 1e6


def sample(server, upstream, load):
    collection_started_at = time.time()
    apps = app_pids() if upstream is None else descendants(upstream.pid)
    limits = [list(resource.prlimit(pid, resource.RLIMIT_NOFILE)) for pid in apps]
    if not limits:
        raise IncompleteSample('empty backend process group')
    if any(limit != [APP_NOFILE, APP_NOFILE] for limit in limits):
        raise RuntimeError(f'backend limits changed during measurement: {limits}')
    app_metrics = process_metrics(apps)
    cpu_group = '/sys/fs/cgroup/tako-apps' if upstream is None else '/sys/fs/cgroup/benchmark-upstream'
    app_metrics['cpu_seconds'] = int(dict(line.split() for line in Path(cpu_group, 'cpu.stat').read_text().splitlines())['usage_usec']) / 1e6
    current = dict(proxy=process_metrics(descendants(server.pid) - apps),
                app_nofile=limits,
                app=app_metrics, loadgen=process_metrics(descendants(load.pid)),
                cpu_seconds=cgroup_cpu(), memory_bytes=int(Path('/sys/fs/cgroup/memory.current').read_text()))
    current.update(collection_started_at=collection_started_at, timestamp=time.time())
    return current


def collect_sample(server, upstream, load):
    started = time.time()
    try:
        current = sample(server, upstream, load)
    except (IncompleteSample, ProcessLookupError) as error:
        # Keep an explicit unavailable observation, then continue if load is alive.
        # A worker exiting during /proc collection need not invalidate the case.
        return dict(collection_started_at=started, timestamp=time.time(),
                    valid=False, unavailable_reason=str(error))
    # Also catches an exit after successful /proc reads. Mark the terminal
    # observation unavailable even if its timestamp is in the window.
    if load.poll() is not None:
        current.update(valid=False, unavailable_reason='load generator exited during collection')
    return current


def collect_samples(server, upstream, load, args, case_dir):
    samples, started = [], time.monotonic()
    try:
        while load.poll() is None:
            if server.poll() is not None:
                raise RuntimeError('proxy exited under load')
            current = collect_sample(server, upstream, load)
            samples.append(current)
            if current.get('valid', True) and (len(samples) - 1) % 5 == 0:
                current['established_tls_port_connections'] = common.established_connections()
            if time.monotonic() - started > args.warmup + args.duration + 180:
                raise RuntimeError('load generator deadline exceeded')
            time.sleep(1)
        return samples
    finally:
        # Preserve complete and unavailable observations even if a later read,
        # process check, or deadline aborts collection.
        write_json(case_dir / 'samples.json', samples)


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


def workflow_state(run_id=None):
    path = DATA / 'apps/bench-features/production/data/tako/workflows.sqlite'
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5) as db:
        if run_id:
            run = db.execute('SELECT status, last_error FROM runs WHERE id = ?', (run_id,)).fetchone()
            ack = db.execute("SELECT COUNT(*) FROM steps WHERE run_id = ? AND name = 'ack'", (run_id,)).fetchone()[0]
            return dict(status=run[0] if run else None, last_error=run[1] if run else None, ack_steps=ack)
        return dict(runs=dict(db.execute('SELECT status, COUNT(*) FROM runs GROUP BY status').fetchall()),
                    ack_steps=db.execute("SELECT COUNT(*) FROM steps WHERE name = 'ack'").fetchone()[0])


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
                            main='src/index.ts', idle_timeout=300,
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
            app_group = Path('/sys/fs/cgroup/benchmark-upstream')
            app_group.mkdir(exist_ok=True)
            def assign_app_group():
                (app_group / 'cgroup.procs').write_text(str(os.getpid()))
            upstream = common.start(['/build/benchapp'], case_dir / 'app.log', env={**ENV, 'PORT': str(port)}, preexec_fn=assign_app_group)
            server = start_proxy(case_dir, proxy, port)
        ready(server, 'status' if feature else 'plaintext')
        app_limits = match_app_limits(upstream)
        # Validate the feature's actual operation before timed load begins.
        if feature:
            response = subprocess.run(['curl', '--http1.1', '--silent', '--show-error', '--fail-with-body', '--max-time', '30',
                '--cacert', '/certs/cert.pem', '--noproxy', '*', '--resolve', 'bench.test:18443:127.0.0.1',
                '-X', 'POST', '-H', 'Content-Type: application/json', '--data', 'ok',
                f'https://bench.test:18443/{endpoint}'], capture_output=True)
            if response.returncode:
                raise RuntimeError(f'feature preflight failed: {response.stdout.decode()} {response.stderr.decode()}')
            payload = json.loads(response.stdout)
            if payload.get('ok') is not True or not payload.get('id'):
                raise RuntimeError(f'feature correctness check failed: {payload}')
            if endpoint == 'workflow-enqueue':
                for _ in range(300):
                    preflight = workflow_state(payload['id'])
                    if preflight['status'] == 'succeeded' and preflight['ack_steps'] == 1:
                        break
                    if preflight['status'] in ['dead', 'cancelled']:
                        raise RuntimeError(f'workflow worker preflight failed: {preflight}')
                    time.sleep(0.1)
                else:
                    raise RuntimeError(f'workflow worker did not persist its ack: {preflight}')
                write_json(case_dir / 'workflow-preflight.json', preflight)
                app_limits.extend(match_app_limits(upstream))
        argv = ['/build/loadgen', '-name', name, '-url', f'https://127.0.0.1:18443/{endpoint}',
                '-host', 'bench.test', '-sni', 'bench.test', '-insecure', '-source-ips', common.SOURCE_IPS,
                '-concurrency', str(concurrency), '-warmup', f'{args.warmup}s',
                '-duration', f'{args.duration}s', '-request-timeout', '60s']
        if feature:
            argv.extend(['-method', 'POST', '-body', 'ok', '-content-type', 'application/json'])
        with (case_dir / 'load.json').open('wb') as output, (case_dir / 'load.stderr').open('wb') as error:
            load = subprocess.Popen(argv, stdout=output, stderr=error, env=ENV)
        samples = collect_samples(server, upstream, load, args, case_dir)
        if load.returncode:
            raise RuntimeError(f'load generator exited {load.returncode}')
        result = json.loads((case_dir / 'load.json').read_text())
        if result['requests'] + result['errors'] <= 0 or sum(result['status_counts'].values()) != result['requests']:
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
                   clean=ok == attempts, completed=True, app_limits=app_limits)
        if endpoint == 'workflow-enqueue':
            row['workflow_after_load'] = workflow_state()
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
        versions=versions, packages=subprocess.check_output(['dpkg-query', '-W', '-f', '${Package} ${Version}\n'], text=True).splitlines(),
        binaries={p.name: hashlib.file_digest(p.open('rb'), 'sha256').hexdigest() for p in Path('/build').iterdir() if p.is_file()},
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
