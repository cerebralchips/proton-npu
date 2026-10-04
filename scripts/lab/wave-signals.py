#!/usr/bin/env python3
"""List FST hierarchy through GTKWave's maintained decoder."""
import json
from pathlib import Path
import subprocess
import sys

wave=Path(sys.argv[1])
p=subprocess.Popen(['fst2vcd',str(wave)],stdout=subprocess.PIPE,text=True)
scope=[]; signals=[]
try:
    for line in p.stdout:
        bits=line.split()
        if not bits: continue
        if bits[0]=='$scope': scope.append(bits[2])
        elif bits[0]=='$upscope': scope.pop()
        elif bits[0]=='$var':
            signals.append({'path':'.'.join([*scope,bits[4]]),'width':int(bits[2]),'id':bits[3]})
        elif bits[0]=='$enddefinitions': break
finally:
    p.stdout.close(); p.terminate(); p.wait()
dest=wave.with_name('signals.json')
dest.write_text(json.dumps(signals,indent=2)+'\n')
for s in signals:
    if any(key in s['path'] for key in ['pc_commit','commit_ack','csr_vl_q','ara_req_valid_o','ara_req_ready_i',
                                       'alu_result_wdata','alu_result_req','alu_result_gnt','waddr_o','we_gpr_o']):
        print(s['path'],s['width'])
print(f'{len(signals)} signals: {dest}')
