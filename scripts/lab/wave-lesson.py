#!/usr/bin/env python3
"""Export a small VCD and annotated snapshots from a verified RTL FST.

Snapshots are taken at falling edges, with combinational handshakes visible for
the following rising edge. The CPU CSV covers commit port 0 only.
"""
import csv
import json
from pathlib import Path
import re
import subprocess
import sys

wave=Path(sys.argv[1]); root=wave.parent
base='TOP.ara_tb_verilator.dut.i_ara_soc.i_system.'
paths={'clk':'TOP.clk_i','rst_n':'TOP.rst_ni','exit':'TOP.exit_o',
       'pc_commit0':base+'i_ariane.pc_commit',
       'commit_ack':base+'i_ariane.commit_ack',
       'scalar_write_enable':base+'i_ariane.commit_stage_i.we_gpr_o',
       'scalar_destinations':base+'i_ariane.commit_stage_i.waddr_o',
       'scalar_write_data':base+'i_ariane.commit_stage_i.wdata_o',
       'vl':base+'i_ara.i_dispatcher.csr_vl_q',
       'vtype':base+'i_ara.i_dispatcher.csr_vtype_q',
       'vector_req_valid':base+'i_ara.i_dispatcher.ara_req_valid_o',
       'vector_req_ready':base+'i_ara.i_dispatcher.ara_req_ready_i',
       'vector_idle':base+'i_ara.i_dispatcher.ara_idle_i',
       'vector_load_complete':base+'i_ara.i_dispatcher.load_complete_i',
       'vector_store_complete':base+'i_ara.i_dispatcher.store_complete_i'}
for lane in range(2):
    for label,signal in [('req','alu_result_req'),('gnt','alu_result_gnt'),
                         ('data','alu_result_wdata'),('address','alu_result_addr'),('byte_enable','alu_result_be')]:
        paths[f'lane{lane}_{label}']=base+f'i_ara.gen_lanes[{lane}].i_lane.'+signal

assembly={}; function=''
for line in (root/'program.dump').read_text().splitlines():
    symbol=re.match(r'^([0-9a-f]+) <(.+)>:',line)
    if symbol: function=symbol[2]
    insn=re.match(r'^\s*([0-9a-f]+):\s+[0-9a-f]+\s+(.+)',line)
    if insn: assembly[int(insn[1],16)]=(function,insn[2].strip())

p=subprocess.Popen(['fst2vcd',str(wave)],stdout=subprocess.PIPE,text=True,bufsize=1024*1024)
scope=[]; signals={}; by_path={v:k for k,v in paths.items()}
for line in p.stdout:
    bits=line.split()
    if not bits: continue
    if bits[0]=='$scope': scope.append(bits[2])
    elif bits[0]=='$upscope': scope.pop()
    elif bits[0]=='$var':
        name='.'.join([*scope,bits[4]])
        if name in by_path: signals[by_path[name]]={'id':bits[3],'width':int(bits[2]),'path':name}
    elif bits[0]=='$enddefinitions': break
missing=set(paths)-set(signals)
if missing:
    p.terminate(); raise SystemExit(f'Waveform signals missing: {missing}')
selected_ids={s['id'] for s in signals.values()}
state={}; now=0; events=[]; vl_changes=[]; previous_vl=None; alu_counts=[0,0]
vcd=(root/'lesson.vcd').open('w')
vcd.write('$comment Selected signals from sim.fst; original 1 ps time scale retained $end\n')
vcd.write('$timescale 1ps $end\n$scope module lesson $end\n')
for name,s in signals.items(): vcd.write(f'$var wire {s["width"]} {s["id"]} {name} $end\n')
vcd.write('$upscope $end\n$enddefinitions $end\n')
commits=(root/'commit-port0.csv').open('w',newline='')
cw=csv.writer(commits); cw.writerow(['sample_time_ps','pc','function','instruction','scalar_write','vl'])
lanes=(root/'vector-lane-writes.csv').open('w',newline='')
lw=csv.writer(lanes); lw.writerow(['sample_time_ps','lane','word_address','data_hex','low_u32','high_u32','byte_enable'])

def val(name):
    bits=state.get(signals[name]['id'],'0')
    return 0 if any(c in bits for c in 'xzXZ') else int(bits,2)

def sample():
    global previous_vl
    if val('clk') or not val('rst_n'): return
    vl=val('vl')
    if vl!=previous_vl:
        vl_changes.append({'time_ps':now,'vl':vl}); previous_vl=vl
    if val('commit_ack')&1:
        pc=val('pc_commit0'); func,insn=assembly.get(pc,('',''))
        reg=val('scalar_destinations')&31
        write=f'x{reg}=0x{val("scalar_write_data")&((1<<64)-1):x}' if val('scalar_write_enable')&1 and reg else ''
        cw.writerow([now,f'0x{pc:x}',func,insn,write,vl])
        if func in ['vector_add','vector_sum'] and insn.startswith('v'):
            events.append({'time_ps':now,'pc':f'0x{pc:x}','function':func,'instruction':insn,'scalar_write':write,'vl':vl})
    for lane in range(2):
        if val(f'lane{lane}_req') and val(f'lane{lane}_gnt'):
            data=val(f'lane{lane}_data')
            lw.writerow([now,lane,val(f'lane{lane}_address'),f'0x{data:016x}',data&0xffffffff,data>>32,f'0x{val(f"lane{lane}_byte_enable"):02x}'])
            alu_counts[lane]+=1

try:
    for line in p.stdout:
        if not line: continue
        first=line[0]
        if first=='#':
            sample(); now=int(line[1:]); vcd.write(line)
        elif first in '01xXzZ':
            code=line[1:].strip()
            if code in selected_ids: state[code]=first; vcd.write(line)
        elif first in 'bB':
            value,code=line[1:].split()
            if code in selected_ids: state[code]=value; vcd.write(line)
        elif line.startswith('$dump'): vcd.write(line)
        elif line.strip()=='$end': vcd.write(line)
    sample()
finally:
    vcd.close(); commits.close(); lanes.close(); p.stdout.close()
if p.wait()!=0: raise SystemExit('FST decoding failed')
summary={'source':wave.name,'timescale':'1 ps (simulation ticks, not hardware frequency)',
         'end_time_ps':now,'signals':signals,'sampling':'falling-edge snapshots; commit port 0 only',
         'vector_instruction_samples':events,'vl_changes':vl_changes,'lane_write_counts':alu_counts}
(root/'wave-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
if not events or min(alu_counts)==0: raise SystemExit('Expected vector execution was not observed')
print(f'Waveform verified: {len(events)} vector instruction samples; lane writes {alu_counts}')
print(f'Beginner waveform: {root/"lesson.vcd"}')
print(json.dumps(events[:12],indent=2))
