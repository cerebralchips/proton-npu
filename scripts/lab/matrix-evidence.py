#!/usr/bin/env python3
"""Check retired machine instructions and matched command/completion events."""
import csv
import json
from pathlib import Path
import re
import sys

def verify(dest):
    dest=Path(dest)
    log=(dest/'rtl.log').read_text()
    header=(Path(__file__).resolve().parents[2]/'examples/scalar_vector_matrix/workload.h').read_text()
    expected=[]
    shapes=re.findall(r'\{(\d+),(\d+),(\d+),raw_(\d+),',header)
    for m,n,k,t in shapes:
        values=re.search(rf'expected_{t}\[\] = \{{([^}}]+)\}}',header)[1]
        checksum=sum(int(x.rstrip('u')) for x in values.split(','))&0xffffffff
        expected.append((int(t),int(m),int(n),int(k),checksum))
    actual=[tuple(map(int,row)) for row in re.findall(r'CASE (\d+) M=(\d+) N=(\d+) K=(\d+) checksum=(\d+) PASS',log)]
    if actual!=expected: raise RuntimeError('Independent workload checksum/case mismatch')
    if 'GUARD PASS: VS-off, illegal encodings, wrong-path, unfenced ordering' not in log:
        raise RuntimeError('Instruction guards missing')
    zero=33+sum(((m+3)//4)*((n+3)//4) for _,m,n,k,_ in expected)
    macc=sum(((m+3)//4)*((n+3)//4)*((k+15)//16) for _,m,n,k,_ in expected)
    events=list(csv.DictReader((dest/'matrix-events.csv').open()))
    if len(events)!=3*(zero+macc): raise RuntimeError(f'Event count mismatch: {len(events)} vs {3*(zero+macc)}')
    issued=[0,0]
    for i in range(0,len(events),3):
        group=events[i:i+3]
        if [e['event'] for e in group]!=['issue','done','response']: raise RuntimeError('Command sequence mismatch')
        if len({e['transaction'] for e in group})!=1: raise RuntimeError('Transaction ID mismatch')
        times=[int(e['cycle']) for e in group]
        if not times[0]<times[1]<times[2]: raise RuntimeError('Completion ordering mismatch')
        op=int(group[0]['operation']); issued[op]+=1
        if times[1]-times[0] != (12 if op else 1): raise RuntimeError('Unexpected matrix execution latency')
    if issued!=[zero,macc]: raise RuntimeError(f'Issued counts wrong: {issued}')
    assembly={}
    for line in (dest/'program.dump').read_text().splitlines():
        match=re.match(r'^\s*([0-9a-f]+):\s+[0-9a-f]+\s+(.+)',line)
        if match: assembly[int(match[1],16)]=match[2].strip()
    counts={'scalar':0,'vector':0,'mzero':0,'mmacc':0}
    with (dest/'instructions.csv').open('w',newline='') as stream:
        out=csv.writer(stream); out.writerow(['cycle','pc','mode','encoding','class','instruction'])
        for line in (dest/'trace_hart_0.dasm').read_text().splitlines():
            match=re.match(r'^\s*(\d+) 0x([0-9a-f]+) ([MSU]) \(0x([0-9a-f]+)\)',line)
            if not match: continue
            cyc,pc,mode,raw=match.groups(); insn=int(raw,16); mnemonic=assembly.get(int(pc,16),'')
            kind='vector' if mnemonic.startswith('v') else 'scalar'
            if (insn&127)==0x2b:
                encoding=insn&~(31<<7)
                if encoding not in [0x2b,0x0200002b]: raise RuntimeError('Reserved matrix instruction retired')
                kind='mmacc' if insn&(1<<25) else 'mzero'
                mnemonic=f'{kind} x{(insn>>7)&31}'
            counts[kind]+=1
            out.writerow([cyc,'0x'+pc,mode,'0x'+raw,kind,mnemonic])
    if counts['mzero']!=zero or counts['mmacc']!=macc: raise RuntimeError(f'Retired/issued mismatch: {counts}')
    if min(counts['scalar'],counts['vector'])<=0: raise RuntimeError('Missing scalar/vector execution')
    result={'cases':actual,'retired_instructions':counts,'matrix_zero':zero,'matrix_macc':macc,
            'matched_issue_done_response':zero+macc,'oracle':'Python integer matmul + scalar C per-element checks',
            'instruction_trace':'instructions.csv','events':'matrix-events.csv'}
    (dest/'execution-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return result

if __name__=='__main__': verify(sys.argv[1])
