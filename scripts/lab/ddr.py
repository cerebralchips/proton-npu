#!/usr/bin/env python3
"""Build and verify the optional SRAM + 4 GiB functional DDR target."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import os
import struct
from run import ROOT, ARA, TOOLS, run_dir, logged, make_args, install_example, rtl_pass
import matrix
sys.path.insert(0, str(ROOT/'tests/memory'))
from elf_image import image, PRELOAD

def build():
    matrix.install()
    source = ROOT / 'hardware/memory/proton_ddr_sim.sv'
    target = ARA / 'hardware/src/memory/proton_ddr_sim.sv'
    target.parent.mkdir(exist_ok=True)
    if not target.exists() or source.read_bytes() != target.read_bytes():
        shutil.copy2(source, target)
    dest = run_dir('ddr-build')
    logged(['make', '-C', 'hardware', 'config=2_lanes', 'matrix=1', 'ddr=1',
            'trace=1', 'buildpath=build-ddr-wave', f'veril_path={TOOLS}/verilator/bin',
            'verilate'], ARA, dest / 'build.log', timeout=3600)
    print('DDR BUILD PASS', flush=True)

def application(latency, stall, trace=False):
    dest = run_dir(f'ddr-l{latency}-s{stall}' + ('-wave' if trace else ''))
    result = {'result': 'INCOMPLETE', 'validation': 'CVA6 + Ara + matrix RTL',
              'sram_base': '0x80000000', 'sram_bytes': 16777216,
              'ddr_base': '0x100000000', 'ddr_bytes': 4294967296,
              'ddr_latency': latency, 'ddr_stall': stall, 'trace': trace,
              'coverage': 'sampled full address range; not an exhaustive byte sweep'}
    try:
        install_example('ddr_memory')
        logged(['make', '-C', 'apps', *make_args(), 'bin/ddr_memory'], ARA, dest / 'compile.log')
        elf = ARA / 'apps/bin/ddr_memory'
        shutil.copy2(elf, dest / 'program.elf')
        shutil.copy2(ARA / 'apps/bin/ddr_memory.dump', dest / 'program.dump')
        sim = ARA / 'hardware/build-ddr-wave/verilator/Vara_tb_verilator'
        preload = dest/'ddr-preload.elf'
        preload.write_bytes(image([(address, struct.pack('<Q', data), 8) for address, data in PRELOAD]))
        result['elf_sha256'] = hashlib.sha256(elf.read_bytes()).hexdigest()
        result['simulator_sha256'] = hashlib.sha256(sim.read_bytes()).hexdigest()
        result['sources_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ['hardware/memory', 'patches', 'examples/ddr_memory']
            for p in sorted((ROOT / folder).rglob('*')) if p.is_file()}
        text = logged([sim, '-c', '3000000', *(['-t'] if trace else []),
                       f'+ddr_latency={latency}', f'+ddr_stall={stall}',
                       f'--load-elf={elf}', f'--load-elf={preload}'], dest, dest / 'rtl.log', timeout=600)
        result['rtl_cycles'] = rtl_pass(text)
        if 'RESULT: PASS ddr_memory' not in text:
            raise RuntimeError('Bare-metal DDR self-check missing')
        if trace:
            waves = list(dest.glob('*.fst'))
            if len(waves) != 1 or not waves[0].stat().st_size:
                raise RuntimeError('Nonempty FST missing')
            logged([sys.executable, ROOT / 'scripts/lab/ddr-wave.py', waves[0]],
                   ROOT, dest / 'wave-check.log', timeout=300)
            result['waveform'] = json.loads((dest / 'ddr-wave-check.json').read_text())
        result['result'] = 'PASS'
        print(text[-1800:], flush=True)
        print('DDR PASS:', dest, flush=True)
    except Exception as error:
        result.update(result='FAIL', error=str(error))
        raise
    finally:
        (dest / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return dest

def loader_checks():
    dest = run_dir('ddr-loader-negative')
    sim = ARA/'hardware/build-ddr-wave/verilator/Vara_tb_verilator'
    checks = []
    cases = [('below-ddr', 0xfffffff8, 8), ('above-ddr', 0x200000000, 8),
             ('cross-ddr-end', 0x1fffffff8, 16), ('above-sram', 0x81000000, 8),
             ('overflow', 0xfffffffffffffff8, 16), ('file-exceeds-memory', 0x100000000, 4)]
    for label, address, size in cases:
        elf = dest/(label+'.elf')
        elf.write_bytes(image([(address, bytes(8), size)]))
        # The upstream command parser can report loader failure with exit status 0.
        # Require its diagnostic and prove simulation never started.
        text = logged([sim, '-c', '20', f'--load-elf={elf}'], dest, dest/(label+'.log'))
        if 'ERROR: Failed to load ELF' not in text or 'Simulation running' in text:
            raise RuntimeError('Invalid ELF was not rejected: '+label)
        checks.append({'case': label, 'result': 'PASS rejected before execution'})
    (dest/'result.json').write_text(json.dumps({'result':'PASS', 'checks':checks}, indent=2)+'\n')
    print('DDR LOADER NEGATIVE PASS:', dest, flush=True)
    return dest

def unit():
    dest = run_dir('ddr-unit')
    result = {'result': 'INCOMPLETE'}
    try:
        logged([TOOLS/'verilator/bin/verilator', '--binary', '--timing', '--assert',
                '--compiler', 'clang', '-j', os.environ.get('NUM_JOBS', '4'),
                '-Wno-fatal', '--top-module', 'ddr_tb', '--Mdir', dest/'obj',
                '-f', ARA/'hardware/build-ddr-wave/verilator/bender_script_2_lanes',
                ROOT/'tests/memory/ddr_tb.sv'], ARA/'hardware', dest/'build.log')
        text = logged([dest/'obj/Vddr_tb', '+ddr_latency=7', '+ddr_stall=3'],
                      dest, dest/'rtl.log', timeout=60)
        if 'DDR UNIT PASS' not in text or '%Error' in text:
            raise RuntimeError('AXI unit gate failed')
        result['result'] = 'PASS'
        print(text, flush=True)
    except Exception as error:
        result.update(result='FAIL', error=str(error))
        raise
    finally:
        (dest/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    return dest

if __name__ == '__main__':
    build()
    if sys.argv[1] == 'ddr-unit':
        unit()
    elif sys.argv[1] != 'ddr-build':
        unit_run = unit()
        loader_run = loader_checks()
        runs = [application(1, 0), application(7, 3, trace=True)]
        combined = matrix.application(
            simulator=ARA/'hardware/build-ddr-wave/verilator/Vara_tb_verilator',
            configuration='2_lanes + MATRIX_ENABLE + PROTON_DDR')
        dest = run_dir('ddr-summary')
        (dest / 'result.json').write_text(json.dumps({'result': 'PASS',
            'unit': str(unit_run.relative_to(ROOT)),
            'loader': str(loader_run.relative_to(ROOT)),
            'combined_matrix': str(combined.relative_to(ROOT)),
            'runs': [str(p.relative_to(ROOT)) for p in runs]}, indent=2) + '\n')
        print('DDR SUITE PASS:', dest)
