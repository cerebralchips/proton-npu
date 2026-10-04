#!/usr/bin/env python3
"""Extract a compact hardware VCD and independently check each tile from FST signals."""
import json
from pathlib import Path
import subprocess
import sys

wave=Path(sys.argv[1]); root=wave.parent
soc='TOP.ara_tb_verilator.dut.i_ara_soc.'
tile=soc+'i_matrix.i_tile.'
paths={'clk':'TOP.clk_i','rst_n':'TOP.rst_ni',
       'cmd_valid':soc+'matrix_cmd_valid','cmd_ready':soc+'matrix_cmd_ready',
       'cmd_macc':soc+'matrix_cmd_macc','done':soc+'matrix_done',
       'step':tile+'step_q','pump':tile+'pump','busy':tile+'active_q',
       'A':tile+'a_q','BT':tile+'bt_q','C':tile+'c_q',
       'pc':soc+'i_system.i_ariane.pc_commit',
       'commit_ack':soc+'i_system.i_ariane.commit_ack',
       'vector_idle':soc+'i_system.ara_matrix_idle'}
for r in range(4):
    for c in range(4):
        base=tile+f'i_mesh.rows[{r}].cols[{c}].pe_inst.'
        for label,name in [('A','data_q'),('B','weight_q'),('partial_in','acc_q'),('partial_out','int_acc_out')]:
            paths[f'PE{r}{c}_{label}']=base+name
p=subprocess.Popen(['fst2vcd',str(wave)],stdout=subprocess.PIPE,text=True,bufsize=1024*1024)
scope=[]; signals={}; wanted={path:name for name,path in paths.items()}
for line in p.stdout:
    bits=line.split()
    if not bits: continue
    if bits[0]=='$scope': scope.append(bits[2])
    elif bits[0]=='$upscope': scope.pop()
    elif bits[0]=='$var':
        path='.'.join([*scope,bits[4]])
        if path in wanted: signals[wanted[path]]={'id':bits[3],'width':int(bits[2]),'path':path}
    elif bits[0]=='$enddefinitions': break
missing=set(paths)-set(signals)
if missing: p.terminate();p.wait();raise SystemExit(f'Missing matrix waveform signals: {missing}')
selected={s['id'] for s in signals.values()}; state={}; time=0
pending=None; checked=0; pumps=0; snapshots=[]
vcd=(root/'matrix.vcd').open('w')
vcd.write('$timescale 1ps $end\n$scope module matrix $end\n')
for name,s in signals.items():vcd.write(f'$var wire {s["width"]} {s["id"]} {name} $end\n')
vcd.write('$upscope $end\n$enddefinitions $end\n')
def val(name):
    bits=state.get(signals[name]['id'],'0')
    if any(c in bits for c in 'xzXZ'): raise RuntimeError(f'Unknown {name} at {time}')
    return int(bits,2)
def words(value,n,bits):return [(value>>(bits*i))&((1<<bits)-1) for i in range(n)]
def signed_byte(x):return x-256 if x>=128 else x
def sample():
    global pending,checked,pumps
    if val('clk') or not val('rst_n'):return
    if val('cmd_valid') and val('cmd_ready'):
        if pending is not None:raise RuntimeError('Overlapping commands in waveform')
        seed=words(val('C'),16,32); op=val('cmd_macc'); pumps=0
        if op:
            a=list(map(signed_byte,words(val('A'),64,8)))
            bt=list(map(signed_byte,words(val('BT'),64,8)))
            expected=[(seed[i*4+j]+sum(a[i*16+k]*bt[j*16+k] for k in range(16)))&0xffffffff
                      for i in range(4) for j in range(4)]
        else:expected=[0]*16
        pending={'start_ps':time,'macc':op,'expected':expected}
    if pending is not None and val('pump'):pumps+=1
    if val('done'):
        if pending is None:raise RuntimeError('Completion without a command in waveform')
        actual=words(val('C'),16,32)
        if actual!=pending['expected']:raise RuntimeError(f'Waveform arithmetic mismatch at {time}')
        if pumps!=(10 if pending['macc'] else 0):raise RuntimeError(f'Waveform pump count mismatch: {pumps}')
        snapshots.append({**pending,'done_ps':time,'pump_count':pumps,'actual':actual})
        checked+=1;pending=None
try:
    for line in p.stdout:
        if line.startswith('#'):
            sample();time=int(line[1:]);vcd.write(line)
        elif line[0] in '01xXzZ':
            code=line[1:].strip()
            if code in selected:state[code]=line[0];vcd.write(line)
        elif line[0] in 'bB':
            bits,code=line[1:].split()
            if code in selected:state[code]=bits;vcd.write(line)
        elif line.startswith('$dump') or line.strip()=='$end':vcd.write(line)
    sample()
finally:vcd.close();p.stdout.close()
if p.wait()!=0:raise SystemExit('FST conversion failed')
expected_commands=json.loads((root/'execution-evidence.json').read_text())['matched_issue_done_response']
if pending is not None or checked!=expected_commands:raise SystemExit(f'Incomplete waveform: checked {checked} commands')
(root/'matrix-wave-check.json').write_text(json.dumps({'result':'PASS','commands':checked,
    'timescale':'1 ps simulator ticks, not physical timing','signals':signals,'tiles':snapshots},indent=2)+'\n')
print(f'WAVEFORM PASS: {checked} commands; every output tile checked against independent arithmetic; {root/"matrix.vcd"}')
