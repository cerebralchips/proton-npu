#!/usr/bin/env python3
"""Check DMA addresses, payloads and handshakes directly from actual FST signals."""
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

wave=Path(sys.argv[1]);root=wave.parent
log=(root/'rtl.log').read_text()
pattern=r'DMA_CASE id=(\d+) src=([0-9a-f]+) dst=([0-9a-f]+) rows=(\d+) cols=(\d+) size=(\d+) ss=(\d+) ds=(\d+) transpose=(\d+) seed=(\d+)'
cases=[];expected=[]
for m in re.findall(pattern,log):
    id,src,dst,rows,cols,size,ss,ds,tr,seed=[int(s,16 if i in [1,2] else 10) for i,s in enumerate(m)]
    cases.append({'id':id,'src':hex(src),'dst':hex(dst),'rows':rows,'cols':cols,'size':size,'transpose':tr})
    e=1<<size
    for r in range(rows):
        for c in range(cols):
            a=src+r*ss+c*e;b=dst+(c*ds+r*e if tr else r*ds+c*e)
            value=sum(((r*ss+c*e+byte)*17+seed & 255)<<(byte*8) for byte in range(e))
            expected.append((id,a,b,size,value))
if len(cases)!=21 or [c['id'] for c in cases]!=list(range(21)): raise ValueError('Missing DMA case manifest')
paths={'clk':'TOP.clk_i','reset':'TOP.rst_ni'}
prefix='TOP.ara_tb_verilator.dut.i_ara_soc.i_dma.'
for n in ['ar_valid','ar_ready','ar_addr','ar_size','r_valid','r_ready','r_data','r_resp','r_last',
          'aw_valid','aw_ready','aw_addr','aw_size','w_valid','w_ready','w_data','w_strb','w_last',
          'b_valid','b_ready','b_resp']:
    paths[n]=prefix+'check_'+n
for n in ['busy','start','valid_config','done_q','error_q','bytes_q']:
    paths[n]=prefix+n
process=subprocess.Popen(['fst2vcd',str(wave)],stdout=subprocess.PIPE,text=True,bufsize=1024*1024)
scopes=[];signals={};wanted={p:n for n,p in paths.items()}
for line in process.stdout:
    words=line.split()
    if not words: continue
    if words[0]=='$scope': scopes.append(words[2])
    elif words[0]=='$upscope': scopes.pop()
    elif words[0]=='$var':
        p='.'.join([*scopes,words[4]])
        if p in wanted: signals[wanted[p]]={'id':words[3],'width':int(words[2]),'path':p}
    elif words[0]=='$enddefinitions': break
if set(signals)!=set(paths):
    process.terminate();process.wait();raise ValueError('Missing DMA probes: '+str(set(paths)-set(signals)))
selected={s['id'] for s in signals.values()};state={};time=0;cycle=0;lastclk=0
ri=0;wi=0;pending_read=None;aw=None;wd=None;stalls=0;starts=0;rejected=0;held={};finish_pending=None;active=False;active_bytes=0;invalid_pending=False
out=(root/'dma-transactions.csv').open('w');writer=csv.writer(out)
writer.writerow(['cycle','case','source','destination','element_bytes','value'])
vcd=(root/'dma.vcd').open('w');vcd.write('$timescale 1ps $end\n$scope module dma $end\n')
for n,s in signals.items(): vcd.write(f'$var wire {s["width"]} {s["id"]} {n} $end\n')
vcd.write('$upscope $end\n$enddefinitions $end\n')
def value(n):
    raw=state.get(signals[n]['id'],'0')
    if any(c in raw for c in 'xXzZ'): raise ValueError(f'Unknown {n}')
    return int(raw,2)
def sample():
    global lastclk,cycle,ri,wi,pending_read,aw,wd,stalls,starts,rejected
    global finish_pending,active,active_bytes,invalid_pending
    clock=value('clk');falling=lastclk and not clock;lastclk=clock
    if not falling or not value('reset'): return
    cycle+=1
    if finish_pending is not None:
        if value('busy') or not value('done_q') or value('error_q') or value('bytes_q')!=finish_pending:
            raise ValueError('DONE/byte count not synchronized with final successful write response')
        finish_pending=None
    if invalid_pending:
        if value('busy') or not value('done_q') or not value('error_q') or value('bytes_q'):
            raise ValueError('Invalid descriptor status/byte count')
        invalid_pending=False
    if active and (not value('busy') or value('done_q') or value('error_q')):
        raise ValueError('DMA completed before final write response')
    if value('start'):

        starts+=1
        if not value('valid_config'): rejected+=1;invalid_pending=True
        else: active=True;active_bytes=0
    for channel,fields in [('ar',['ar_addr','ar_size']),('aw',['aw_addr','aw_size']),('w',['w_data','w_strb','w_last'])]:
        payload=tuple(value(n) for n in fields)
        if channel in held and (not value(channel+'_valid') or payload!=held[channel]):
            raise ValueError('DMA payload changed under backpressure: '+channel)
        if value(channel+'_valid') and not value(channel+'_ready'):
            held[channel]=payload;stalls+=1
        else: held.pop(channel,None)
    if value('ar_valid') and value('ar_ready'):
        if pending_read is not None or ri>=len(expected): raise ValueError('Unexpected DMA read')
        ex=expected[ri]
        if (value('ar_addr'),value('ar_size'))!=(ex[1],ex[3]): raise ValueError('Wrong DMA source address/size')
        pending_read=ex
    if value('r_valid') and value('r_ready'):
        if pending_read is None: raise ValueError('Unmatched DMA read response')
        _,src,dst,size,data=pending_read;e=1<<size
        actual=(value('r_data')>>((src&7)*8)) & ((1<<(e*8))-1)
        if actual!=data or value('r_resp') or not value('r_last'): raise ValueError('DMA read data/response mismatch')
        pending_read=None;ri+=1
    if value('aw_valid') and value('aw_ready'):
        if aw is not None or wi>=len(expected): raise ValueError('Unexpected DMA AW')
        ex=expected[wi]
        aw=(value('aw_addr'),value('aw_size'))
        if aw!=(ex[2],ex[3]): raise ValueError('Wrong DMA destination address/size (transpose)')
    if value('w_valid') and value('w_ready'):
        if wd is not None or wi>=len(expected): raise ValueError('Unexpected DMA W')
        _,src,dst,size,data=expected[wi];e=1<<size;mask=((1<<e)-1)<<(dst&7)
        actual=(value('w_data')>>((dst&7)*8)) & ((1<<(e*8))-1)
        if actual!=data or value('w_strb')!=mask or not value('w_last'): raise ValueError('DMA write data/strobe mismatch')
        wd=actual
    if value('b_valid') and value('b_ready'):
        if aw is None or wd is None or value('b_resp') or ri!=wi+1: raise ValueError('DMA write completion mismatch')
        id,src,dst,size,data=expected[wi]
        writer.writerow([cycle,id,hex(src),hex(dst),1<<size,hex(data)])
        wi+=1;aw=None;wd=None;active_bytes+=1<<size
        if wi==len(expected) or expected[wi][0]!=id:
            finish_pending=active_bytes;active=False
try:
    for line in process.stdout:
        if line.startswith('#'):
            sample();time=int(line[1:]);vcd.write(line)
        elif line[0] in '01xXzZ':
            code=line[1:].strip()
            if code in selected: state[code]=line[0];vcd.write(line)
        elif line[0] in 'bB':
            bits,code=line[1:].split()
            if code in selected: state[code]=bits;vcd.write(line)
    sample()
except BaseException:
    process.terminate();process.wait();raise
finally:
    out.close();vcd.close();process.stdout.close()
if process.wait()!=0: raise ValueError('FST conversion did not complete')
if ri!=len(expected) or wi!=len(expected) or pending_read or aw or wd or held or value('busy'):
    raise ValueError('Incomplete DMA waveform')
if starts!=27 or rejected!=6 or not stalls: raise ValueError(f'Coverage: starts={starts}, rejected={rejected}, stalls={stalls}')
result={'result':'PASS','cases':cases,'read_elements':ri,'write_elements':wi,
        'payload_bytes':sum(1<<e[3] for e in expected),'starts':starts,'rejected_descriptors':rejected,
        'request_backpressure_cycles':stalls,'completion_and_byte_counts_checked':True,'max_address':hex(max(max(e[1],e[2])+(1<<e[3])-1 for e in expected)),
        'transactions_sha256':hashlib.sha256((root/'dma-transactions.csv').read_bytes()).hexdigest(),
        'signals':signals}
(root/'dma-wave-check.json').write_text(json.dumps(result,indent=2)+'\n')
print(f'DMA WAVEFORM PASS: {ri} reads, {wi} writes, copy/transpose addresses and payloads independently checked')
