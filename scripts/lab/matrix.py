#!/usr/bin/env python3
"""Matrix gates. All models use real RTL; evidence is retained on failure."""
import hashlib
import json
import os
import shutil
import re
import subprocess
from pathlib import Path
import sys
from run import ROOT, ARA, TOOLS, run_dir, logged, make_args, install_example, rtl_pass, SMOKE

RTL = ROOT/'hardware/matrix'
SOURCES = [RTL/'quadrilatero_pkg.sv',
           *[RTL/'vendor/quadrilatero'/f'quadrilatero_{n}.sv' for n in ['mac_int','pe','mesh']],
           RTL/'matrix_tile.sv', RTL/'matrix_axi_lite.sv', RTL/'matrix_router.sv']

def unit():
    dest = run_dir('matrix-unit')
    result = {'result':'INCOMPLETE','gate':'integer PE, tile, AXI-Lite and router',
              'test_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in (ROOT/'tests/matrix').glob('*') if p.is_file()},
              'rtl_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES}}
    try:
        logged([sys.executable,ROOT/'tests/matrix/generate.py',dest/'vectors.hex'],ROOT,dest/'oracle.log')
        logged([TOOLS/'verilator/bin/verilator','--binary','--timing','--assert',
                '--compiler','clang','-j',os.environ.get('NUM_JOBS','4'),
                '-Wno-fatal','--top-module','tile_tb','--Mdir',dest/'obj',
                *SOURCES,ROOT/'tests/matrix/tile_tb.sv'],ROOT,dest/'build.log')
        text=logged([dest/'obj/Vtile_tb',f'+vectors={dest}/vectors.hex'],dest,dest/'rtl.log',timeout=60)
        for marker in ['GATE PE PASS:', 'GATE TILE PASS:']:
            if marker not in text: raise RuntimeError(f'Missing {marker}')
        if '%Error' in text: raise RuntimeError('RTL assertion failure')
        for top, marker in [('bus_tb','GATE BUS PASS:'),('router_tb','GATE ROUTER PASS:')]:
            logged([TOOLS/'verilator/bin/verilator','--binary','--timing','--assert',
                    '--compiler','clang','-j',os.environ.get('NUM_JOBS','4'),'-Wno-fatal',
                    '--top-module',top,'--Mdir',dest/top,*SOURCES,ROOT/'tests/matrix'/f'{top}.sv'],
                   ROOT,dest/f'{top}-build.log')
            gate=logged([dest/top/f'V{top}'],dest,dest/f'{top}.log',timeout=60)
            if marker not in gate or '%Error' in gate: raise RuntimeError(f'{top} failed')
            print(gate,flush=True)
        result['result']='PASS'
        for line in text.splitlines():
            if line.startswith('GATE '): print(line,flush=True)
        print(f'MATRIX UNIT PASS: {dest}',flush=True)
    except Exception as e:
        result.update(result='FAIL',error=str(e)); raise
    finally: (dest/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return dest

def install():
    pins=json.loads((ROOT/'sources.lock.json').read_text())
    for name,directory in [('ara',ARA),('cva6',ARA/'hardware/deps/cva6')]:
        actual=subprocess.check_output(['git','-C',directory,'rev-parse','HEAD'],text=True).strip()
        if actual!=pins[name]['commit']: raise RuntimeError(f'{name} revision differs from source lock')
    provenance=json.loads((RTL/'vendor/quadrilatero/provenance.json').read_text())
    for name,digest in provenance['files'].items():
        if hashlib.sha256((RTL/'vendor/quadrilatero'/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError(f'Vendored source changed: {name}')
    logged(['bash',ROOT/'scripts/lab/apply-patches.sh'],ROOT,run_dir('matrix-install')/'patches.log')
    # Copy only changed inputs: stable timestamps preserve incremental builds.
    target=ARA/'hardware/src/matrix'
    for p in RTL.rglob('*'):
        if not p.is_file(): continue
        q=target/p.relative_to(RTL)
        if not q.exists() or q.read_bytes()!=p.read_bytes():
            q.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,q)

def model(trace=False):
    return ARA/'hardware'/('build-matrix-wave' if trace else 'build-matrix')/'verilator/Vara_tb_verilator'

def build(trace=False):
    install()
    dest=run_dir('matrix-build-wave' if trace else 'matrix-build')
    cmd=['make','-C','hardware','config=2_lanes','matrix=1',
         f'buildpath={"build-matrix-wave" if trace else "build-matrix"}',
         f'veril_path={TOOLS}/verilator/bin']
    if trace: cmd.append('trace=1')
    logged([*cmd,'verilate'],ARA,dest/'build.log',timeout=3600)
    if not model(trace).is_file(): raise RuntimeError('Missing matrix model')
    print(f'MATRIX BUILD PASS: {model(trace)}',flush=True)
    return dest

def application(app='scalar_vector_matrix',trace=False,max_cycles=3000000,inject=False):
    dest=run_dir('matrix-wave' if trace else 'matrix-run-'+app)
    result={'result':'INCOMPLETE','application':app,'configuration':'2_lanes + MATRIX_ENABLE',
            'sources':json.loads((ROOT/'sources.lock.json').read_text()),
            'rtl_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES},
            'patch_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'patches').rglob('*.patch')}}
    try:
        install_example(app)
        if app=='scalar_vector_matrix':
            logged([sys.executable,ROOT/'tests/matrix/workload.py',dest/'workload.h'],ROOT,dest/'workload-oracle.log')
            if (dest/'workload.h').read_bytes()!=(ROOT/'examples/scalar_vector_matrix/workload.h').read_bytes():
                raise RuntimeError('Committed workload data differs from independent generator')
            for p in (ROOT/'examples'/app).iterdir():
                if p.is_file(): shutil.copy2(p,dest/p.name)
        args=['make','-C','apps',*make_args()]
        # Upstream does not track all header/flag dependencies. Recompile only
        # our app translation units, including when toggling failure injection.
        if app=='scalar_vector_matrix':
            for p in sorted((ROOT/'examples'/app).iterdir()):
                if p.suffix in {'.c','.S'}: args+=['-W',f'{app}/{p.name}']
        if inject: args+=['ENV_DEFINES=-DINJECT_FAILURE=1']
        logged([*args,f'bin/{app}'],ARA,dest/'compile.log')
        elf=ARA/'apps/bin'/app
        shutil.copy2(elf,dest/'program.elf')
        shutil.copy2(ARA/'apps/bin'/f'{app}.dump',dest/'program.dump')
        result['elf_sha256']=hashlib.sha256(elf.read_bytes()).hexdigest()
        result['simulator_sha256']=hashlib.sha256(model(trace).read_bytes()).hexdigest()
        cmd=[model(trace),'-c',str(max_cycles)]
        if trace: cmd+=['-t']
        text=logged([*cmd,'-l',f'ram,{elf},elf'],dest,dest/'rtl.log',timeout=300)
        result['rtl_cycles']=rtl_pass(text)
        if app=='scalar_vector_matrix':
            if 'RESULT: PASS scalar_vector_matrix' not in text: raise RuntimeError('Combined program self-check missing')
            logged([sys.executable,ROOT/'scripts/lab/matrix-evidence.py',dest],ROOT,dest/'evidence-check.log')
            result['execution']=json.loads((dest/'execution-evidence.json').read_text())
        if trace:
            waves=list(dest.glob('*.fst'))
            if len(waves)!=1 or not waves[0].stat().st_size: raise RuntimeError('Missing FST')
            if app=='scalar_vector_matrix':
                logged([sys.executable,ROOT/'scripts/lab/matrix-wave.py',waves[0]],ROOT,dest/'wave-check.log',timeout=300)
            result['waveform']=waves[0].name
        result['result']='PASS'
        for line in text.splitlines():
            if any(marker in line for marker in ['CVA6 + Ara','GUARD PASS','CASE ','RESULT:','Executed cycles:']):
                print(line,flush=True)
        print(f'MATRIX RTL PASS: {dest}',flush=True)
    except Exception as e:
        result.update(result='FAIL',error=str(e)); raise
    finally: (dest/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return dest

def negative_checks():
    dest=run_dir('matrix-negative'); outcomes=[]
    for label,kwargs in [('wrong-result',{'inject':True}),('cycle-timeout',{'max_cycles':20})]:
        try:
            application(**kwargs)
        except RuntimeError as e:
            # Accept only the intended failure; compile problems are not a passing negative test.
            latest=max((ROOT/'artifacts').glob('*matrix-run-scalar_vector_matrix-*'),key=lambda p:p.stat().st_mtime)
            text=(latest/'rtl.log').read_text() if (latest/'rtl.log').exists() else ''
            marker='RESULT: FAIL case=0 element=0' if label=='wrong-result' else 'Simulation timeout'
            if marker not in text: raise RuntimeError(f'Unexpected {label} failure: {e}')
            outcomes.append({'test':label,'result':'PASS: intended failure rejected','evidence':str(latest.relative_to(ROOT))})
        else: raise RuntimeError(f'Negative check unexpectedly passed: {label}')
    (dest/'result.json').write_text(json.dumps({'result':'PASS','checks':outcomes},indent=2)+'\n')
    print(f'NEGATIVE GATES PASS: {dest}',flush=True)
    return dest

if __name__=='__main__':
    try:
        if sys.argv[1]=='matrix-unit': unit()
        elif sys.argv[1]=='matrix-build': build()
        elif sys.argv[1] in ['matrix','matrix-wave','matrix-smoke','matrix-negative']:
            wave=sys.argv[1]=='matrix-wave'
            unit()
            build(wave)
            if sys.argv[1]=='matrix-smoke':
                dest=run_dir('matrix-smoke'); results=[]
                for app in SMOKE:
                    evidence=application(app)
                    results.append({'test':app,'result':'PASS','evidence':str(evidence.relative_to(ROOT))})
                    (dest/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
                print(f'MATRIX SMOKE PASS: {len(results)}/{len(SMOKE)} {dest}',flush=True)
            elif sys.argv[1]=='matrix-negative': negative_checks()
            else: application(trace=wave)
        else: raise ValueError('Unknown matrix command')
    except Exception as e:
        print(f'FAIL: {e}',file=sys.stderr); sys.exit(1)
