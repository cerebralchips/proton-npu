#!/usr/bin/env python3
"""Resolve host/guest paths without accidentally selecting a failed run."""
import json
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
kind=sys.argv[1] if len(sys.argv)>1 else 'run'
if kind not in {'run','wave','fst','matrix','matrix-wave','matrix-fst','matrix-elf'}:
    raise SystemExit('Use run, wave, fst, matrix, matrix-wave, matrix-fst, or matrix-elf')
for p in sorted((root/'artifacts').glob('*/result.json'),reverse=True):
    data=json.loads(p.read_text())
    if data.get('result')!='PASS': continue
    if not data.get('application'): continue
    if kind.startswith('matrix'):
        if data.get('application')!='scalar_vector_matrix': continue
        name={'matrix-wave':'matrix.vcd','matrix-fst':data.get('waveform'),'matrix-elf':'program.elf'}.get(kind)
        if kind=='matrix': print(p.parent); break
        if name and (p.parent/name).is_file(): print(p.parent/name); break
        continue
    if kind=='run': print(p.parent); break
    name=data.get('lesson_waveform' if kind=='wave' else 'waveform')
    if name and (p.parent/name).is_file(): print(p.parent/name); break
else: raise SystemExit(f'No successful {kind} artifact found')
