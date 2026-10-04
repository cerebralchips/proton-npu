#!/usr/bin/env python3
"""Build and validate real CVA6+Ara RTL runs, retaining reproducible evidence."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
ARA = ROOT / 'upstream/ara'
TOOLS = Path(os.environ['LAB_TOOLS'])
SMOKE = ['rv64ui-ara-add', 'rv64um-ara-mul', 'rv64uv-ara-vsetvli',
         'rv64uv-ara-vadd', 'rv64uv-ara-vmul', 'rv64uv-ara-vredsum',
         'rv64uv-ara-vle32', 'rv64uv-ara-vse32', 'rv64uv-ara-vfadd']

def run_dir(label):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return Path(tempfile.mkdtemp(prefix=f'{stamp}-{label}-', dir=ROOT/'artifacts'))

def logged(cmd, directory, logfile, timeout=1800):
    print(f'{logfile.name}: {logfile}', flush=True)
    with logfile.open('w') as stream:
        stream.write(f'$ {shlex.join(map(str, cmd))}\n'); stream.flush()
        try:
            result = subprocess.run(list(map(str,cmd)), cwd=directory,
                                    stdout=stream, stderr=subprocess.STDOUT,
                                    timeout=timeout)
        except subprocess.TimeoutExpired:
            stream.write('\nLAB FAILURE: wall-clock timeout\n')
            raise RuntimeError(f'Timeout; inspect {logfile}')
    text = logfile.read_text(errors='replace')
    if result.returncode:
        print('\n'.join(text.splitlines()[-25:]), flush=True)
        raise RuntimeError(f'Exit {result.returncode}; inspect {logfile}')
    return text

def make_args():
    gcc = Path(os.environ.get('ARA_GCC_ROOT',str(Path.home()/'.local/share/cva6-lab/gcc-13.1.0')))
    return ['config=2_lanes',f'LLVM_INSTALL_DIR={TOOLS}/riscv-llvm',
            f'ISA_SIM_INSTALL_DIR={TOOLS}/spike',
            f'RISCV_CC_GCC={gcc}/bin/riscv-none-elf-gcc',
            'LLVM_V_FLAGS=-fno-vectorize -fno-slp-vectorize -mllvm -scalable-vectorization=off -mllvm -riscv-v-vector-bits-min=0 -mno-implicit-float']

def model(trace=False):
    return ARA/'hardware'/('build-lab-wave' if trace else 'build-lab')/'verilator/Vara_tb_verilator'

def build(trace=False):
    dest = run_dir('build-wave' if trace else 'build')
    args = ['make','-C','hardware', 'config=2_lanes',
            f'buildpath={"build-lab-wave" if trace else "build-lab"}',
            f'veril_path={TOOLS}/verilator/bin']
    if trace: args.append('trace=1')
    args.append('verilate')
    logged(args,ARA,dest/'build.log',timeout=3600)
    if not model(trace).is_file(): raise RuntimeError('Simulator binary missing')
    print(f'BUILD PASS: {model(trace)}',flush=True)
    return dest

def install_example(app):
    source = ROOT/'examples'/app
    if source.is_dir():
        dest = ARA/'apps'/app
        dest.mkdir(exist_ok=True)
        for p in source.iterdir():
            if p.suffix in {'.c','.h','.S'}: shutil.copy2(p,dest/p.name)

def rtl_pass(text):
    if '*** SUCCESS ***' not in text:
        raise RuntimeError('RTL completion marker missing (a zero exit code alone is insufficient)')
    if re.search(r'\*\*\* FAILED \*\*\*|Simulation timeout|%Error|RESULT: FAIL',text):
        raise RuntimeError('RTL reported failure or timeout')
    m = re.search(r'^Executed cycles:\s*([0-9]+)\s*$',text,re.MULTILINE)
    if not m or int(m[1]) <= 0: raise RuntimeError('Missing/nonpositive RTL cycle count')
    return int(m[1])

def check_demo(text):
    found = [(int(n),int(s)) for n,s in re.findall(r'CASE n=(\d+) sum=(\d+) PASS',text)]
    expected = [(n,(3*n*n-n)//2) for n in [0,1,7,63,64,65,127,128,129,257]]
    if found != expected or 'RESULT: PASS scalar_vector cases=10' not in text:
        raise RuntimeError('Missing/incorrect demo results')
    return found

def run_app(app,trace=False,reference=False,inject=False,max_cycles=2000000):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',app): raise ValueError('Invalid application name')
    if not model(trace).is_file(): build(trace)
    dest = run_dir(('wave-' if trace else 'run-')+app+('-negative' if inject else ''))
    manifest = {'application':app,'configuration':'2_lanes','lanes':2,'vlen_bits':2048,
                'validation':'RTL self-check', 'result':'INCOMPLETE', 'trace':trace,
                'max_cycles':max_cycles,'injected_failure':inject,
                'sources':json.loads((ROOT/'sources.lock.json').read_text())}
    manifest['patch_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted((ROOT/'patches/ara').glob('*.patch'))}
    manifest_path = dest/'result.json'
    try:
        install_example(app)
        args=['make','-C','apps',*make_args()]
        if inject: args += ['ENV_DEFINES=-DINJECT_FAILURE=1']
        logged([*args,f'bin/{app}'],ARA,dest/'compile.log')
        binary=ARA/'apps/bin'/app
        shutil.copy2(binary,dest/'program.elf')
        dump=ARA/'apps/bin'/f'{app}.dump'
        if dump.exists(): shutil.copy2(dump,dest/'program.dump')
        if (ROOT/'examples'/app/'main.c').exists():
            shutil.copy2(ROOT/'examples'/app/'main.c',dest/'main.c')
        manifest['elf_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
        command=[model(trace),'-c',str(max_cycles)]
        if trace: command.append('-t')
        # The upstream utility parses options in multiple passes; keep -l last.
        command.extend(['-l',f'ram,{binary},elf'])
        text=logged(command,dest,dest/'rtl.log',timeout=300)
        manifest['rtl_cycles']=rtl_pass(text)
        if app=='hello_world' and 'Ariane says Hello!' not in text:
            raise RuntimeError('Hello message missing')
        if app=='scalar_vector':
            manifest['cases']=check_demo(text)
            assembly=(dest/'program.dump').read_text()
            for op in ['vadd.vv','vredsum.vs','vle32.v','vse32.v']:
                if op not in assembly: raise RuntimeError(f'RVV instruction missing: {op}')
        if reference:
            logged([*args,f'bin/{app}.spike'],ARA,dest/'compile-spike.log')
            spike_binary=ARA/'apps/bin'/f'{app}.spike'
            shutil.copy2(spike_binary,dest/'program.spike.elf')
            spike=logged([TOOLS/'spike/bin/spike','--isa=rv64gcv_zfh_zvfh_zvl2048b',spike_binary],
                         dest,dest/'spike.log',timeout=300)
            if app=='scalar_vector':
                if check_demo(spike)!=manifest['cases']: raise RuntimeError('RTL/Spike result mismatch')
            elif app=='hello_world' and 'Ariane says Hello!' not in spike:
                raise RuntimeError('Spike hello message missing')
            manifest['validation']='RTL self-check + Spike application-result comparison (separate runtime ELFs)'
        if trace:
            waves=list(dest.glob('*.fst'))
            if len(waves)!=1 or waves[0].stat().st_size==0: raise RuntimeError('Nonempty FST missing')
            manifest['waveform']=waves[0].name
            if app=='scalar_vector':
                logged([sys.executable,ROOT/'scripts/lab/wave-lesson.py',waves[0]],
                       ROOT,dest/'wave-analysis.log',timeout=180)
                manifest['lesson_waveform']='lesson.vcd'
                manifest['instruction_samples']='commit-port0.csv'
                manifest['vector_writes']='vector-lane-writes.csv'
        manifest['result']='PASS'
        for line in text.splitlines():
            if any(s in line for s in ['CVA6 + Ara','CASE n=','RESULT:','Ariane says','Executed cycles:']): print(line)
        print(f'PASS {app}: {manifest["rtl_cycles"]} RTL cycles\nEvidence: {dest}',flush=True)
    except Exception as e:
        manifest['result']='FAIL'; manifest['error']=str(e)
        raise
    finally:
        manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    return dest

def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['build','hello','run','wave','smoke'])
    p.add_argument('app',nargs='?',default='scalar_vector')
    p.add_argument('--inject-failure',action='store_true')
    p.add_argument('--max-cycles',type=int,default=2000000)
    a=p.parse_args()
    if a.command!='build': build(trace=a.command=='wave')
    if a.command=='build': build()
    elif a.command=='smoke':
        dest=run_dir('smoke'); results=[]
        for app in SMOKE:
            try:
                run=run_app(app)
                results.append({'test':app,'result':'PASS','evidence':str(run.relative_to(ROOT))})
            except Exception as e:
                results.append({'test':app,'result':'FAIL','error':str(e)})
            (dest/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
        print(f'{sum(r["result"]=="PASS" for r in results)}/{len(results)} smoke cases passed: {dest}')
        if any(r['result']!='PASS' for r in results): return 1
    else:
        app='hello_world' if a.command=='hello' else a.app
        run_app(app,trace=a.command=='wave',reference=app in {'hello_world','scalar_vector'},
                inject=a.inject_failure,max_cycles=a.max_cycles)
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except Exception as e:
        print(f'FAIL: {e}',file=sys.stderr); sys.exit(1)
