#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[2]
ara=root/'upstream/ara'
tools=Path(os.environ['LAB_TOOLS'])
lock=json.loads((root/'sources.lock.json').read_text())

def output(cmd,cwd=None):
    return subprocess.check_output(list(map(str,cmd)),cwd=cwd,stderr=subprocess.STDOUT,text=True).strip()

report={'configuration':{'name':'2_lanes','lanes':2,'vlen_bits':2048},'revisions':{},'tools':{}}
for name,folder in [('ara',ara),('cva6',ara/'hardware/deps/cva6'),
                    ('verilator',ara/'toolchain/verilator'),('spike',ara/'toolchain/riscv-isa-sim')]:
    head=output(['git','rev-parse','HEAD'],folder)
    if head!=lock[name]['commit']: raise SystemExit(f'{name}: unexpected revision {head}')
    report['revisions'][name]=head
report['tools']['clang']=output([tools/'riscv-llvm/bin/clang','--version'])
report['tools']['verilator']=output([tools/'verilator/bin/verilator','--version'])
report['tools']['bender']=output([tools/'bin/bender','--version'])
gcc=Path(os.environ.get('ARA_GCC_ROOT',str(Path.home()/'.local/share/cva6-lab/gcc-13.1.0')))
report['tools']['gcc']=output([gcc/'bin/riscv-none-elf-gcc','--version']).splitlines()[0]
report['runtime_libraries']={}
for lib in ['libc.a','libm.a','libgcc.a']:
    path=Path(output([gcc/'bin/riscv-none-elf-gcc','-march=rv64gc','-mabi=lp64d',f'-print-file-name={lib}']))
    report['runtime_libraries'][lib]={'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
report['patches']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'patches/ara').glob('*.patch'))}
report['ara_tracked_changes']=output(['git','diff','--stat'],ara)
report['fst2vcd']=output(['sh','-c','command -v fst2vcd'])
report['result']='PASS'
text=json.dumps(report,indent=2)+'\n'
(root/'artifacts/doctor.json').write_text(text)
print(text)
