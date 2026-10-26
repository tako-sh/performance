#!/usr/bin/env python3
"""Full-server memory comparison, run only in the disposable test container."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import socket
import subprocess
import time

OUT = Path('/results')
DATA = Path('/opt/tako')
APP = 'bench-http/production'
SOCKET = '/var/run/tako/bench.sock'
SOURCE_IPS = ','.join(f'127.0.0.{i}' for i in range(2, 18))


def command(payload):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(120)
        sock.connect(SOCKET)
        sock.sendall(json.dumps(payload).encode() + b'\n')
        data = b''
        while b'\n' not in data:
            chunk = sock.recv(65536)
            if not chunk:
                raise RuntimeError('management socket closed without a response')
            data += chunk
    response = json.loads(data)
    if response.get('status') != 'ok':
        raise RuntimeError(response)
    return response


def memory(pid):
    fields = {}
    for line in Path(f'/proc/{pid}/smaps_rollup').read_text().splitlines()[1:]:
        key, value, *_ = line.split()
        fields[key.rstrip(':')] = int(value)
    stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    return dict(pss_kib=fields['Pss'], rss_kib=fields['Rss'],
                private_kib=sum(fields.get(k, 0) for k in ('Private_Clean', 'Private_Dirty', 'Private_Hugetlb')),
                cpu_seconds=(int(stat[11]) + int(stat[12])) / os.sysconf('SC_CLK_TCK'))


def established_connections():
    count = 0
    for table in ('tcp', 'tcp6'):
        for line in Path(f'/proc/net/{table}').read_text().splitlines()[1:]:
            fields = line.split()
            if fields[1].endswith(f':{18443:04X}') and fields[3] == '01':
                count += 1
    return count


def stop(proc):
    if proc is None or proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def start(argv, log, **kwargs):
    with log.open('wb') as output:
        return subprocess.Popen(argv, stdout=output, stderr=subprocess.STDOUT, **kwargs)


def ready(proc):
    for _ in range(200):
        if proc.poll() is not None:
            raise RuntimeError('server exited during startup; inspect case log')
        test = subprocess.run(['curl', '--http1.1', '--silent', '--show-error', '--fail', '--cacert', '/certs/cert.pem',
                               '--noproxy', '*', '--resolve', 'bench.test:18443:127.0.0.1',
                               'https://bench.test:18443/plaintext'], capture_output=True)
        if test.returncode == 0 and test.stdout == b'hello, world\n':
            return
        time.sleep(0.1)
    raise RuntimeError(f'HTTPS readiness failed: {test.stderr.decode()} body={test.stdout!r}')


def prepare():
    Path('/certs').mkdir(exist_ok=True)
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2',
                    '-subj', '/CN=bench.test', '-addext', 'subjectAltName=DNS:bench.test',
                    '-keyout', '/certs/key.pem', '-out', '/certs/cert.pem'],
                   check=True, capture_output=True)
    certs = DATA / 'certs/bench.test'
    certs.mkdir(parents=True, exist_ok=True)
    shutil.copy('/certs/cert.pem', certs / 'fullchain.pem')
    shutil.copy('/certs/key.pem', certs / 'privkey.pem')
    Path('/Caddyfile').write_text('''{
 auto_https off
 admin off
}
https://bench.test:18443 {
 tls /certs/cert.pem /certs/key.pem
 rate_limit {
  zone per_ip {
   key {remote_host}
   events 65535
   window 1s
  }
 }
 reverse_proxy 127.0.0.1:9101
}
''')


def case(args, variant, concurrency, repetition):
    name = f'r{repetition}-{variant}-c{concurrency}'
    case_dir = OUT / name
    case_dir.mkdir()
    server = upstream = load = None
    try:
        if variant == 'caddy':
            upstream = start(['/build/benchapp'], case_dir / 'app.log',
                             env={**os.environ, 'PORT': '9101', 'GOMAXPROCS': '2'})
            server = start(['/build/caddy', 'run', '--config', '/Caddyfile', '--adapter', 'caddyfile'],
                           case_dir / 'server.log', env={**os.environ, 'GOMAXPROCS': '2'})
        else:
            Path(SOCKET).unlink(missing_ok=True)
            server = start(['/usr/local/bin/tako-server', '--data-dir', str(DATA),
                            '--socket', SOCKET, '--http-port', '18080', '--https-port', '18443',
                            '--metrics-port', '0', '--no-acme'], case_dir / 'server.log',
                           env={**os.environ, 'TAKO_BENCH_L4_READ_BYTES': str(int(variant[5:]) * 1024)})
            for _ in range(300):
                if Path(SOCKET).exists():
                    break
                if server.poll() is not None:
                    raise RuntimeError('Tako exited before management socket was ready')
                time.sleep(0.1)
            # Deploy a real native app through the server's normal provisioning path.
            release = DATA / f'apps/{APP}/releases/{name}'
            release.mkdir(parents=True)
            shutil.copy('/build/benchapp', release / 'benchapp')
            (release / 'app.json').write_text(json.dumps(dict(
                protocol_version=0, runtime='go', main='benchapp', start=['./benchapp'],
                idle_timeout=300, env_vars={'TAKO_BUILD': name, 'GOMAXPROCS': '2'})))
            command(dict(command='deploy', app=APP, version=name, path=str(release),
                         routes=['bench.test'], source_ip='direct', secrets={}, storages={}))
            command(dict(command='scale', app=APP, instances=1))
        ready(server)
        time.sleep(1)
        baseline = memory(server.pid)
        argv = ['/build/loadgen', '-name', name, '-url', 'https://127.0.0.1:18443/plaintext',
                '-host', 'bench.test', '-sni', 'bench.test', '-insecure',
                '-source-ips', SOURCE_IPS, '-concurrency', str(concurrency),
                '-warmup', f'{args.warmup}s', '-duration', f'{args.duration}s',
                '-request-timeout', '60s']
        with (case_dir / 'load.json').open('wb') as output, (case_dir / 'load.stderr').open('wb') as error:
            load = subprocess.Popen(argv, stdout=output, stderr=error,
                                    env={**os.environ, 'GOMAXPROCS': '2'})
        samples = []
        started = time.monotonic()
        while load.poll() is None:
            sample = memory(server.pid)
            sample['elapsed_seconds'] = round(time.monotonic() - started, 3)
            if len(samples) % 20 == 0:
                sample['established_tls_port_connections'] = established_connections()
            samples.append(sample)
            if sample['elapsed_seconds'] > args.warmup + args.duration + 150:
                raise RuntimeError('load generator exceeded deadline')
            time.sleep(0.25)
        if load.returncode:
            raise RuntimeError(f'load generator exited {load.returncode}')
        result = json.loads((case_dir / 'load.json').read_text())
        time.sleep(2)
        after = memory(server.pid)
        summary = dict(name=name, variant=variant, concurrency=concurrency, repetition=repetition,
                       baseline=baseline, after_close=after,
                       peak={k: max(s[k] for s in samples) for k in ('pss_kib', 'rss_kib', 'private_kib')},
                       process_cpu_seconds=samples[-1]['cpu_seconds']-baseline['cpu_seconds'],
                       samples_include_warmup=True, load=result,
                       success=result['requests'] > 0 and result['errors'] == 0
                       and set(result['status_counts']) == {'200'}
                       and result['bytes'] == 13 * result['requests'])
        (case_dir / 'samples.json').write_text(json.dumps(samples, indent=2) + '\n')
        (case_dir / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(dict(name=name, pss_mib=round(summary['peak']['pss_kib']/1024, 1),
                              rps=round(result['requests_per_sec']), success=summary['success'])), flush=True)
        return summary
    finally:
        stop(load)
        stop(server)
        stop(upstream)
        # The disposable cgroup contains only this benchmark's app processes.
        app_groups = Path('/sys/fs/cgroup/tako-apps')
        if app_groups.exists():
            for kill in app_groups.rglob('cgroup.kill'):
                kill.write_text('1')
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--concurrency', default='5000,20000')
    parser.add_argument('--variants', default='tako-64,tako-32,tako-16,caddy')
    parser.add_argument('--repetitions', type=int, default=2)
    parser.add_argument('--warmup', type=int, default=5)
    parser.add_argument('--duration', type=int, default=20)
    args = parser.parse_args()
    metadata = dict(kernel=platform.release(), architecture=platform.machine(),
                    cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
                    memory_max=Path('/sys/fs/cgroup/memory.max').read_text().strip(),
                    swap_max=Path('/sys/fs/cgroup/memory.swap.max').read_text().strip(),
                    openssl=subprocess.check_output(['openssl', 'version'], text=True).strip(),
                    binaries={p.name: hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()
                              for p in Path('/build').iterdir() if p.is_file()},
                    arguments=vars(args))
    (OUT / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    prepare()
    results = []
    variants = args.variants.split(',')
    for repetition in range(1, args.repetitions + 1):
        for concurrency in map(int, args.concurrency.split(',')):
            for variant in variants if repetition % 2 else reversed(variants):
                results.append(case(args, variant, concurrency, repetition))
                (OUT / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    if not all(r['success'] for r in results):
        raise SystemExit('One or more cases had failed requests; inspect summary.json')


if __name__ == '__main__':
    main()
