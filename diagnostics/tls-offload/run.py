#!/usr/bin/env python3
"""Measure established-request latency at matched background TLS arrival rates."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import statistics
import time

spec=importlib.util.spec_from_file_location('buffers','/perf/diagnostics/buffer-lifetime/run.py')
buffers=importlib.util.module_from_spec(spec);spec.loader.exec_module(buffers)
base=buffers.base
OUT=Path('/results')
VARIANTS=('baseline','offload1','offload2','caddy')


def case(args,variant,background_rate,repetition,sequence):
    name=f'r{repetition}-{variant}-bg{background_rate}'
    directory=OUT/name;directory.mkdir()
    server=upstream=primary=background=None
    try:
        os.environ['TAKO_BENCH_TLS_OFFLOAD']=variant[-1] if variant.startswith('offload') else '0'
        server,upstream=buffers.start_proxy(variant if variant in ('baseline','caddy') else 'tls',directory,sequence)
        base.ready(server);time.sleep(1)
        common=['/build/buffer-load','-protocol','h1','-workload','small','-duration',f'{args.duration}s']
        primary_phase=directory/'primary-phase.json';background_phase=directory/'background-phase.json'
        primary=base.start(common+['-workers','128','-warmup','1s' if args.smoke else '3s','-rate','1000','-phase-file',str(primary_phase)],
                           directory/'primary.json',env={**os.environ,'GOMAXPROCS':'2'})
        if background_rate:
            background=base.start(common+['-workers','64','-warmup','0s','-rate',str(background_rate),'-churn','-phase-file',str(background_phase)],
                                  directory/'background.json',env={**os.environ,'GOMAXPROCS':'2'})
        started=time.monotonic();samples=[];before=None
        while primary.poll() is None or (background is not None and background.poll() is None):
            sample=base.memory(server.pid)
            sample.update(elapsed=time.monotonic()-started,phase=buffers.phase(primary_phase))
            if before is None and sample['phase']=='ready' and (background is None or buffers.phase(background_phase)=='ready'):
                before=sample.copy()
                Path(str(primary_phase)+'.start').write_text('start')
                if background is not None: Path(str(background_phase)+'.start').write_text('start')
            status=Path(f'/proc/{server.pid}/status').read_text().splitlines()
            sample['threads']=int(next(line for line in status if line.startswith('Threads:')).split()[1])
            samples.append(sample)
            if sample['elapsed']>180: raise RuntimeError('TLS test exceeded deadline')
            time.sleep(.25)
        after=base.memory(server.pid)
        foreground=json.loads((directory/'primary.json').read_text())
        bg=json.loads((directory/'background.json').read_text()) if background is not None else None
        success=primary.returncode==0 and foreground['errors']==0 and foreground['requests']==1000*args.duration
        if bg is not None:
            success=success and background.returncode==0 and bg['errors']==0 and bg['requests']==background_rate*args.duration and bg['handshakes']==bg['requests']
        measured=[s for s in samples if s['phase']=='measuring']
        record=dict(name=name,variant=variant,background_rate=background_rate,repetition=repetition,primary=foreground,background=bg,
                    success=success and before is not None and bool(measured),peak_pss_kib=max(s['pss_kib'] for s in samples))
        if measured:
            record['median_pss_kib']=statistics.median(s['pss_kib'] for s in measured)
            record['threads']=max(s['threads'] for s in measured)
        if before is not None:
            record['measured_cpu_seconds']=after['cpu_seconds']-before['cpu_seconds']
            total=foreground['requests']+(bg['requests'] if bg is not None else 0)
            record['cpu_microseconds_per_total_request']=record['measured_cpu_seconds']*1e6/total
        (directory/'samples.json').write_text(json.dumps(samples,indent=2)+'\n')
        (directory/'summary.json').write_text(json.dumps(record,indent=2)+'\n')
        print(json.dumps(dict(name=name,success=record['success'],p99_ms=foreground['latency_ms']['p99'],pss_mib=record.get('median_pss_kib',0)/1024)),flush=True)
        return record
    finally:
        for process in (primary,background,server,upstream): base.stop(process)
        for kill in Path('/sys/fs/cgroup/tako-apps').glob('**/cgroup.kill'): kill.write_text('1')
        time.sleep(1)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--repetitions',type=int,default=4)
    parser.add_argument('--duration',type=int,default=15)
    parser.add_argument('--rates',default='0,1500,2500')
    parser.add_argument('--variants',default=','.join(VARIANTS))
    parser.add_argument('--smoke',action='store_true')
    args=parser.parse_args()
    if args.smoke: args.duration=2
    variants=args.variants.split(',');rates=[int(rate) for rate in args.rates.split(',')]
    if not set(variants).issubset(VARIANTS) or args.duration<1 or min(rates)<0: parser.error('invalid case selection')
    (OUT/'metadata.json').write_text(json.dumps(dict(arguments=vars(args),kernel=platform.release(),architecture=platform.machine(),
        cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),memory_max=Path('/sys/fs/cgroup/memory.max').read_text().strip(),
        swap_max=Path('/sys/fs/cgroup/memory.swap.max').read_text().strip(),runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        binaries={p.name:hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in Path('/build').iterdir() if p.is_file()}),indent=2)+'\n')
    base.prepare();records=[]
    for repetition in range(1,args.repetitions+1):
        for rate in rates:
            for variant in variants if repetition%2 else reversed(variants):
                try: record=case(args,variant,rate,repetition,len(records)+1)
                except Exception as error:
                    record=dict(variant=variant,background_rate=rate,repetition=repetition,success=False,error_type=type(error).__name__)
                    print(json.dumps(record),flush=True)
                records.append(record);(OUT/'summary.json').write_text(json.dumps(records,indent=2)+'\n')
    if not all(r['success'] for r in records): raise SystemExit('failed or incomplete TLS cases')

if __name__=='__main__': main()
