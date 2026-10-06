#!/usr/bin/env python3
"""Build and verify the separate programmable DMA simulation target."""
import hashlib
import json
import os
import shutil
import sys
import subprocess
from run import ROOT, ARA, TOOLS, run_dir, logged, make_args, install_example, rtl_pass
import matrix

def build():
    matrix.install()
    for folder in ['dma','memory']:
        for p in (ROOT/'hardware'/folder).glob('*.sv'):
            q=ARA/'hardware/src'/folder/p.name
            q.parent.mkdir(exist_ok=True)
            if not q.exists() or p.read_bytes()!=q.read_bytes(): shutil.copy2(p,q)
    dest=run_dir('dma-build')
    logged(['make','-C','hardware','config=2_lanes','matrix=1','ddr=1','dma=1',
            'trace=1','buildpath=build-dma-wave',f'veril_path={TOOLS}/verilator/bin','verilate'],
           ARA,dest/'build.log',timeout=3600)
    print('DMA BUILD PASS',flush=True)

def unit():
    dest=run_dir('dma-unit')
    logged([TOOLS/'verilator/bin/verilator','--binary','--timing','--assert','--compiler','clang',
            '-j',os.environ.get('NUM_JOBS','4'),'-Wno-fatal','--top-module','dma_tb',
            '--Mdir',dest/'obj','-f',ARA/'hardware/build-dma-wave/verilator/bender_script_2_lanes',
            ROOT/'tests/dma/dma_tb.sv'],ARA/'hardware',dest/'build.log',timeout=600)
    text=logged([dest/'obj/Vdma_tb'],dest,dest/'rtl.log',timeout=60)
    if 'DMA UNIT PASS' not in text or '%Error' in text: raise RuntimeError('DMA unit failed')
    (dest/'result.json').write_text(json.dumps({'result':'PASS','log':text},indent=2)+'\n')
    print(text,flush=True)
    return dest

def application(latency,stall,trace):
    dest=run_dir(f'dma-l{latency}-s{stall}')
    result={'result':'INCOMPLETE','latency':latency,'stall':stall,'trace':trace}
    try:
        install_example('dma_transfer')
        logged(['make','-C','apps',*make_args(),'bin/dma_transfer'],ARA,dest/'compile.log')
        elf=ARA/'apps/bin/dma_transfer'
        shutil.copy2(elf,dest/'program.elf')
        shutil.copy2(ARA/'apps/bin/dma_transfer.dump',dest/'program.dump')
        sim=ARA/'hardware/build-dma-wave/verilator/Vara_tb_verilator'
        result['elf_sha256']=hashlib.sha256(elf.read_bytes()).hexdigest()
        result['simulator_sha256']=hashlib.sha256(sim.read_bytes()).hexdigest()
        text=logged([sim,'-c','3000000',*(['-t'] if trace else []),f'--load-elf={elf}',
                     f'+ddr_latency={latency}',f'+ddr_stall={stall}'],dest,dest/'rtl.log',timeout=600)
        result['rtl_cycles']=rtl_pass(text)
        if 'RESULT: PASS dma_transfer' not in text: raise RuntimeError('DMA self-check missing')
        if trace:
            wave=next(dest.glob('*.fst'))
            logged([sys.executable,ROOT/'scripts/lab/dma-wave.py',wave],ROOT,dest/'wave-check.log',timeout=600)
            result['waveform']=json.loads((dest/'dma-wave-check.json').read_text())
        result['result']='PASS'
        print(text[-2500:],flush=True)
    except Exception as e:
        result.update(result='FAIL',error=str(e));raise
    finally: (dest/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return dest

def negative(positive):
    dest=run_dir('dma-negative')
    # Use the original FST unchanged, with an intentionally incorrect oracle seed.
    wave=next(positive.glob('*.fst'))
    os.link(wave,dest/'sim.fst')
    text=(positive/'rtl.log').read_text()
    assert 'transpose=0 seed=7' in text
    (dest/'rtl.log').write_text(text.replace('transpose=0 seed=7','transpose=0 seed=8',1))
    p=subprocess.run([sys.executable,ROOT/'scripts/lab/dma-wave.py',dest/'sim.fst'],
                     cwd=ROOT,capture_output=True,text=True,timeout=120)
    (dest/'checker.log').write_text(p.stdout+p.stderr)
    if p.returncode==0 or 'DMA read data/response mismatch' not in p.stderr:
        raise RuntimeError('Corrupt DMA oracle did not fail for the expected reason')
    sim=ARA/'hardware/build-dma-wave/verilator/Vara_tb_verilator'
    timeout=logged([sim,'-c','20',f'--load-elf={positive}/program.elf'],dest,dest/'timeout.log',timeout=60)
    if 'Simulation timeout' not in timeout: raise RuntimeError('Timeout injection missing')
    try: rtl_pass(timeout)
    except RuntimeError: pass
    else: raise RuntimeError('Timed-out DMA run incorrectly accepted')
    result={'result':'PASS','checks':['corrupt expected payload rejected from original FST',
                                    '20-cycle simulator timeout rejected']}
    (dest/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('DMA NEGATIVE PASS:',dest,flush=True)
    return dest

if __name__=='__main__':
    build()
    if sys.argv[1]=='dma-unit': unit()
    elif sys.argv[1]=='dma-test':
        u=unit()
        runs=[application(1,0,False),application(7,3,True)]
        neg=negative(runs[1])
        combined=matrix.application(trace=True,simulator=ARA/'hardware/build-dma-wave/verilator/Vara_tb_verilator',
                                   configuration='2_lanes + MATRIX_ENABLE + PROTON_DDR + PROTON_DMA')
        out=run_dir('dma-summary')
        sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                 for folder in ['hardware/dma','examples/dma_transfer','tests/dma','patches']
                 for p in sorted((ROOT/folder).rglob('*')) if p.is_file()}
        sources.update({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in [ROOT/'scripts/lab/dma.py',ROOT/'scripts/lab/dma-wave.py']})
        (out/'result.json').write_text(json.dumps({'result':'PASS','sources_sha256':sources,
            'unit':str(u.relative_to(ROOT)),'negative':str(neg.relative_to(ROOT)),'runs':[str(p.relative_to(ROOT)) for p in runs],
            'combined_matrix':str(combined.relative_to(ROOT))},indent=2)+'\n')
        print('DMA SUITE PASS:',out)
