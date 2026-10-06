#!/usr/bin/env python3
"""Dense RVV DDR sweeps on real CPU/Ara RTL, with bounded and explicit full modes."""
import argparse
import hashlib
import json
import re
import shutil
import struct
import sys
import time
from run import ROOT, ARA, run_dir, logged, make_args, install_example, rtl_pass
import ddr

DDR_BYTES = 1 << 32
SRAM_STAGE_BYTES = 14 << 20


def number(value):
    return int(value, 0)


def check_elf(path):
    """Keep loadable program/BSS segments below the staging area and its guard."""
    raw = path.read_bytes()
    phoff = struct.unpack_from('<Q', raw, 32)[0]
    phsize, phnum = struct.unpack_from('<HH', raw, 54)
    for index in range(phnum):
        kind, _, _, _, address, _, size, _ = struct.unpack_from(
            '<IIQQQQQQ', raw, phoff + index*phsize)
        if kind == 1 and size and not (0x80000000 <= address < address+size <= 0x800ffff8):
            raise RuntimeError('Program overlaps SRAM staging reservation')


def application(mode, size, offset=0, stage_bytes=4096, stage_base=0x80100000,
                latency=1, stall=0, trace=False, inject=False, timeout=600,
                vector_init=False, max_cycles_override=None):
    dest = run_dir(f'ddr-sweep-{mode}' + ('-negative' if inject else ''))
    result = dict(result='INCOMPLETE', mode=mode, bytes=size, offset=offset,
                  stage_bytes=stage_bytes if mode == 'staged' else 0,
                  stage_base=hex(stage_base), ddr_start=hex((1 << 32) + offset),
                  ddr_latency=latency, ddr_stall=stall, trace=trace,
                  injected_failure=inject, full_4gib_completed=False,
                  initialization='vector (diagnostic)' if vector_init else 'scalar',
                  validation='Real CVA6 + two-lane Ara + matrix RTL; dense range, scalar oracle')
    manifest = dest/'result.json'
    try:
        install_example('ddr_sweep')
        defines = (f'-DSTAGED={int(mode == "staged")} -DSWEEP_BYTES={size}UL '
                   f'-DSWEEP_OFFSET={offset}UL -DSTAGE_BYTES={stage_bytes}UL '
                   f'-DSTAGE_BASE={stage_base}UL -DINJECT_FAILURE={int(inject)} '
                   f'-DVECTOR_INIT={int(vector_init)}')
        logged(['make', '-C', 'apps', *make_args(), f'ENV_DEFINES={defines}',
                '-W', 'ddr_sweep/main.c', 'bin/ddr_sweep'], ARA, dest/'compile.log')
        elf = dest/'program.elf'
        shutil.copy2(ARA/'apps/bin/ddr_sweep', elf)
        shutil.copy2(ARA/'apps/bin/ddr_sweep.dump', dest/'program.dump')
        check_elf(elf)
        assembly = (dest/'program.dump').read_text()
        for instruction in ['vle64.v', 'vse64.v', 'vxor.vx']:
            if instruction not in assembly:
                raise RuntimeError('Missing explicit RVV instruction: ' + instruction)
        oracle = re.search(r'<verify>:\n(.*?)(?=\n[0-9a-f]+ <|\Z)', assembly, re.S)
        if not oracle or re.search(r'\tv[a-z0-9]+\.', oracle[1]) or '\tld\t' not in oracle[1]:
            raise RuntimeError('Verification must use scalar loads, with no vector instructions')
        sim = ARA/'hardware/build-ddr-wave/verilator/Vara_tb_verilator'
        result['elf_sha256'] = hashlib.sha256(elf.read_bytes()).hexdigest()
        result['simulator_sha256'] = hashlib.sha256(sim.read_bytes()).hexdigest()
        result['sources_sha256'] = {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ['examples/ddr_sweep', 'hardware/memory', 'patches']
            for p in sorted((ROOT/folder).rglob('*')) if p.is_file()}
        # Upstream -c parses a signed 32-bit int. Omit it for large sweeps rather
        # than silently overflowing; the wall-clock watchdog always remains.
        max_cycles = max_cycles_override or (1_000_000 + size * (20 + latency + stall))
        cycle_args = ['-c', str(max_cycles)] if max_cycles <= 0x7fffffff else []
        result.update(cycle_limit=max_cycles if cycle_args else None, timeout_seconds=timeout)
        manifest.write_text(json.dumps(result, indent=2)+'\n')
        started = time.monotonic()
        try:
            text = logged([sim, *cycle_args, *(['-t'] if trace else []),
                           f'+ddr_latency={latency}', f'+ddr_stall={stall}',
                           f'--load-elf={elf}'], dest, dest/'rtl.log', timeout=timeout)
        except RuntimeError as error:
            # The simulator propagates the bare-metal nonzero return value.
            expected_code = 1 if mode == 'staged' else 3
            if not inject or not str(error).startswith(f'Exit {expected_code};'):
                raise
            text = (dest/'rtl.log').read_text()
        result['wall_seconds'] = time.monotonic() - started
        if inject:
            bad_address = hex((1 << 32) + offset + size - 8)[2:]
            marker = f'RESULT: FAIL ddr_sweep mode={mode} address={bad_address} '
            if (marker not in text or '*** FAILED ***' not in text or
                    '*** SUCCESS ***' in text or 'Simulation timeout' in text or '%Error' in text):
                raise RuntimeError('Corruption was not rejected at the expected address')
            result['result'] = 'PASS (expected corruption detected)'
        else:
            result['rtl_cycles'] = rtl_pass(text)
            chunks = (size + stage_bytes - 1)//stage_bytes if mode == 'staged' else 1
            marker = (f'RESULT: PASS ddr_sweep mode={mode} bytes={size} '
                      f'chunks={chunks} checked_words={size//8}')
            if marker not in text:
                raise RuntimeError('Incorrect/missing dense sweep self-check')
            result['chunks'] = chunks
            times = re.search(r'SWEEP_CYCLES init=(\d+) transfer=(\d+) verify=(\d+)', text)
            if not times: raise RuntimeError('Missing phase timing')
            result['phase_cycles'] = dict(zip(['init', 'transfer', 'verify'], map(int, times.groups())))
            if trace:
                waves = list(dest.glob('*.fst'))
                if len(waves) != 1 or not waves[0].stat().st_size:
                    raise RuntimeError('Nonempty FST missing')
                logged([sys.executable, ROOT/'scripts/lab/ddr-wave.py', waves[0],
                        '--sweep', manifest], ROOT, dest/'wave-check.log', timeout=300)
                result['waveform'] = json.loads((dest/'ddr-wave-check.json').read_text())
            result['full_4gib_completed'] = size == DDR_BYTES and offset == 0
            result['result'] = 'PASS'
        print(text[-1400:], flush=True)
        print('DDR SWEEP:', dest, flush=True)
    except Exception as error:
        result.update(result='FAIL', error=str(error))
        raise
    finally:
        manifest.write_text(json.dumps(result, indent=2)+'\n')
    return dest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['ddr-sweep', 'ddr-sweep-smoke'])
    parser.add_argument('--mode', choices=['direct', 'staged', 'both'], default='both')
    size = parser.add_mutually_exclusive_group()
    size.add_argument('--bytes', type=number, default=65560)
    size.add_argument('--full', action='store_true', help='Explicit 4 GiB run; very large time/RAM cost')
    parser.add_argument('--offset', type=number, default=0)
    parser.add_argument('--stage-bytes', type=number, default=None)
    parser.add_argument('--latency', type=int, default=1)
    parser.add_argument('--stall', type=int, default=0)
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--vector-init', action='store_true', help='Reproduce the unresolved vector producer stall')
    parser.add_argument('--max-cycles', type=int, help='Optional 1..2147483647 cycle watchdog')
    parser.add_argument('--timeout', type=int, default=600, help='Wall seconds per simulation')
    args = parser.parse_args()
    size = DDR_BYTES if args.full else args.bytes
    stage_bytes = args.stage_bytes if args.stage_bytes is not None else (SRAM_STAGE_BYTES if args.full else 4096)
    if size <= 0 or size % 8 or args.offset < 0 or args.offset % 8 or args.offset+size > DDR_BYTES:
        parser.error('Size/offset must be 8-byte aligned and fit inside 4 GiB DDR')
    if not 0 < stage_bytes <= SRAM_STAGE_BYTES or stage_bytes % 8:
        parser.error('Staging size must be 8-byte aligned, 8 bytes through 14 MiB')
    if not 1 <= args.latency <= 1024 or not 0 <= args.stall <= 1024 or args.timeout <= 0:
        parser.error('Invalid delay or timeout')
    if args.max_cycles is not None and not 1 <= args.max_cycles <= 0x7fffffff:
        parser.error('Cycle watchdog must fit a positive signed 32-bit integer')
    if args.trace and size > (1 << 20):
        parser.error('Use bounded traces (at most 1 MiB) to avoid enormous waveform files')
    ddr.build()
    runs = []
    if args.command == 'ddr-sweep-smoke':
        # Tail in the final RVV operation and after 16 reuses of the SRAM buffer.
        for mode in ['direct', 'staged']:
            runs.append(application(mode, 65560))
            runs.append(application(mode, 65560, DDR_BYTES-65560, latency=7, stall=3,
                                    stage_base=0x80eff000, trace=True))
            runs.append(application(mode, 1048, DDR_BYTES-1048, stage_bytes=256, inject=True))
        # Larger untraced samples for a more useful full-sweep extrapolation.
        for mode in ['direct', 'staged']:
            runs.append(application(mode, 262168))
    else:
        for mode in (['direct', 'staged'] if args.mode == 'both' else [args.mode]):
            runs.append(application(mode, size, args.offset, stage_bytes, latency=args.latency,
                                    stall=args.stall, trace=args.trace, timeout=args.timeout,
                                    vector_init=args.vector_init, max_cycles_override=args.max_cycles))
    dest = run_dir('ddr-sweep-summary')
    summary = dict(result='PASS', runs=[str(p.relative_to(ROOT)) for p in runs])
    if args.command == 'ddr-sweep-smoke':
        estimates = {}
        for path in runs[-2:]:
            r = json.loads((path/'result.json').read_text())
            phase = sum(r['phase_cycles'].values())
            full_cycles = phase * DDR_BYTES / r['bytes']
            estimates[r['mode']] = dict(sample_bytes=r['bytes'], sample_wall_seconds=r['wall_seconds'],
                projected_cycles=round(full_cycles),
                projected_hours=full_cycles / (r['rtl_cycles']/r['wall_seconds']) / 3600)
        summary['full_4gib_estimates'] = estimates
        summary['estimate_limits'] = ('Linear extrapolation, not a completed 4 GiB run. The current '
            'per-word associative DDR storage consumes much more than 4 GiB host RAM when full; '
            'the 8 GiB VM is insufficient. Paging or a larger host is needed. Large-map lookup, '
            'allocation and SRAM chunk size can change runtime. No physical DDR performance claim.')
    (dest/'result.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2), flush=True)
    print('DDR SWEEP SUITE PASS:', dest, flush=True)


if __name__ == '__main__':
    main()
