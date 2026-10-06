#!/usr/bin/env python3
"""Live, timed bare-metal DDR/SRAM vector addition on the actual CPU/Ara RTL."""
import argparse
import hashlib
import json
import os
import re
import selectors
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import time
from run import ROOT, ARA, install_example, logged, make_args, rtl_pass, run_dir
import ddr


def timed_run(command, dest, timeout):
    """Tee line-buffered simulator output live, time only execution, reap on Ctrl-C."""
    command = ['/usr/bin/time', '-p', '-o', str(dest/'simulator-time.txt'),
               'stdbuf', '-oL', '-eL', *map(str, command)]
    deadline = time.monotonic() + timeout
    with (dest/'rtl.log').open('w') as logfile:
        logfile.write('$ ' + shlex.join(command) + '\n'); logfile.flush()
        process = subprocess.Popen(command, cwd=dest, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    if time.monotonic() > deadline:
                        raise RuntimeError(f'Simulator wall timeout after {timeout} seconds')
                    for key, _ in selector.select(timeout=1):
                        data = os.read(key.fd, 65536)
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        text = data.decode(errors='replace')
                        logfile.write(text); logfile.flush()
                        print(text, end='', flush=True)
            code = process.wait(timeout=5)
        except BaseException:
            # time/stdbuf/simulator share this group; do not leave a CPU job running.
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.wait()
            raise
        finally:
            process.stdout.close()
    timing = (dest/'simulator-time.txt').read_text()
    match = re.search(r'^real ([0-9.]+)$', timing, re.M)
    if not match: raise RuntimeError('Missing /usr/bin/time measurement')
    print('SIMULATOR TIME (Linux /usr/bin/time -p):\n' + timing, flush=True)
    return code, (dest/'rtl.log').read_text(), float(match[1])


def application(elements, passes=1, latency=1, stall=0, inject=False,
                timeout=600, max_cycles=None, expected_failure=None):
    dest = run_dir('ddr-add' + ('-negative' if inject else ''))
    manifest = dest/'result.json'
    result = dict(result='INCOMPLETE', elements=elements, passes=passes, chunk_words=1024,
                  ddr_buffer_bytes=elements*4, total_ddr_data_bytes=elements*12,
                  sram_scratch_bytes=3*1025*4, ddr_latency=latency, ddr_stall=stall,
                  injected_failure=inject, waveforms=False, instruction_logs=False,
                  validation='CVA6 + Ara RTL; explicit RVV copies/addition; scalar per-element oracle')
    try:
        install_example('ddr_vector_add')
        defines = f'-DELEMENTS={elements}UL -DPASSES={passes}UL -DINJECT_FAILURE={int(inject)}'
        logged(['make', '-C', 'apps', *make_args(), 'ENV_DEFINES='+defines,
                '-W', 'ddr_vector_add/main.c', 'bin/ddr_vector_add'], ARA, dest/'compile.log')
        elf = dest/'program.elf'
        shutil.copy2(ARA/'apps/bin/ddr_vector_add', elf)
        shutil.copy2(ARA/'apps/bin/ddr_vector_add.dump', dest/'program.dump')
        # Check that text/data/BSS, including scratch arrays, fit below the SRAM stack reservation.
        raw = elf.read_bytes()
        phoff = struct.unpack_from('<Q', raw, 32)[0]
        phsize, phnum = struct.unpack_from('<HH', raw, 54)
        for i in range(phnum):
            kind, _, _, _, address, _, size, _ = struct.unpack_from('<IIQQQQQQ', raw, phoff+i*phsize)
            if kind == 1 and size and not (0x80000000 <= address < address+size <= 0x80f00000):
                raise RuntimeError('Program/scratch buffers exceed the SRAM reservation')
        assembly = (dest/'program.dump').read_text()
        for instruction in ['vle32.v', 'vse32.v', 'vadd.vv']:
            if instruction not in assembly: raise RuntimeError('Missing RVV instruction: '+instruction)
        oracle = re.search(r'<verify>:\n(.*?)(?=\n[0-9a-f]+ <|\Z)', assembly, re.S)
        if not oracle or re.search(r'\tv[a-z0-9]+\.', oracle[1]) or '\tlwu\t' not in oracle[1]:
            raise RuntimeError('Expected independent scalar verification in disassembly')
        sim = ARA/'hardware/build-ddr-wave/verilator/Vara_tb_verilator'
        result.update(elf_sha256=hashlib.sha256(raw).hexdigest(),
                      simulator_sha256=hashlib.sha256(sim.read_bytes()).hexdigest())
        result['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ['examples/ddr_vector_add', 'hardware/memory', 'patches']
            for p in sorted((ROOT/folder).rglob('*')) if p.is_file()}
        # No waveform flag. Discard always-on debug instruction/dispatch dumps;
        # retain the executable, disassembly, live UART log, timing and result JSON.
        for name in ['trace_hart_0.dasm', 'accelerator-dispatch.csv', 'matrix-events.csv']:
            (dest/name).symlink_to('/dev/null')
        budget = max_cycles or (2_000_000 + elements*passes*(256 + 12*(latency+stall)))
        limit = ['-c', str(budget)] if budget <= 0x7fffffff else []
        result.update(cycle_limit=budget if limit else None, timeout_seconds=timeout)
        manifest.write_text(json.dumps(result, indent=2)+'\n')
        print(f'\nRUN: {elements:,} elements/buffer, {passes} pass(es), '
              f'{elements*12:,} DDR data bytes; no waveforms\nARTIFACTS: {dest}', flush=True)
        code, text, seconds = timed_run([sim, *limit, f'+ddr_latency={latency}',
            f'+ddr_stall={stall}', f'--load-elf={elf}'], dest, timeout)
        result.update(simulator_exit_code=code, simulator_wall_seconds=seconds)
        if expected_failure:
            if expected_failure == 'mismatch':
                if (code != 1 or f'RESULT: FAIL ddr_vector_add pass=0 index={elements-1} ' not in text
                        or '*** FAILED ***' not in text or '*** SUCCESS ***' in text):
                    raise RuntimeError('Deliberate output corruption was not detected')
            elif expected_failure == 'timeout':
                if 'Simulation timeout' not in text or '*** SUCCESS ***' in text:
                    raise RuntimeError('Forced cycle timeout was not rejected')
            else: raise ValueError('Unknown expected failure')
            result['result'] = 'PASS expected ' + expected_failure + ' detected'
        else:
            if code: raise RuntimeError(f'Simulator exited {code}; inspect rtl.log above')
            result['rtl_cycles'] = rtl_pass(text)
            expected = (f'RESULT: PASS ddr_vector_add elements={elements} passes={passes} '
                        f'checked_outputs={elements*passes}')
            if expected not in text: raise RuntimeError('Missing full program self-check')
            checks = re.findall(r'^CHECK (\d+)/(\d+) OK: (\d+) results match; inputs and guards intact$', text, re.M)
            if checks != [(str(i+1), str(passes), str(elements)) for i in range(passes)]:
                raise RuntimeError('One or more complete per-pass checks are missing')
            counts = re.search(r'ADD_CYCLES init=(\d+) copies_and_add=(\d+) verify=(\d+)', text)
            if not counts: raise RuntimeError('Missing phase cycles')
            result['phase_cycles'] = dict(zip(['init', 'copies_and_add', 'verify'], map(int, counts.groups())))
            result['checked_outputs'] = elements*passes
            result['result'] = 'PASS'
        print('DDR ADD ' + result['result'] + ': ' + str(dest), flush=True)
    except BaseException as error:
        result.update(result='FAIL', error=str(error) or type(error).__name__)
        raise
    finally:
        manifest.write_text(json.dumps(result, indent=2)+'\n')
    return dest, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['ddr-add', 'ddr-add-test'])
    parser.add_argument('--elements', type=int, help='32-bit elements per A/B/C buffer (default 4099; timed mode 16387)')
    duration = parser.add_mutually_exclusive_group()
    duration.add_argument('--passes', type=int)
    duration.add_argument('--target-seconds', type=int, help='Calibrate two passes, then size a separate run toward this duration')
    parser.add_argument('--latency', type=int, default=1)
    parser.add_argument('--stall', type=int, default=0)
    parser.add_argument('--inject-failure', action='store_true', help='Corrupt the last output: command must fail')
    parser.add_argument('--timeout', type=int, help='Wall watchdog per simulation (default max(600, 2*target))')
    parser.add_argument('--max-cycles', type=int, help='Optional positive signed-32-bit cycle watchdog')
    args = parser.parse_args()
    elements = args.elements if args.elements is not None else (16387 if args.target_seconds else 4099)
    passes = args.passes if args.passes is not None else 1
    timeout = args.timeout if args.timeout is not None else max(600, 2*(args.target_seconds or 0))
    if not 1 <= elements <= 1048576 or not 1 <= passes <= 100000:
        parser.error('Use 1..1048576 elements and 1..100000 passes')
    if args.target_seconds is not None and not 10 <= args.target_seconds <= 86400:
        parser.error('Target duration must be 10..86400 seconds')
    if args.target_seconds and (args.inject_failure or args.max_cycles):
        parser.error('Calibrated mode cannot combine with deliberate failure/watchdog overrides')
    if timeout <= 0 or not 1 <= args.latency <= 1024 or not 0 <= args.stall <= 1024:
        parser.error('Invalid watchdog or DDR delay')
    if args.max_cycles is not None and not 1 <= args.max_cycles <= 0x7fffffff:
        parser.error('Cycle watchdog must fit a positive signed 32-bit integer')
    ddr.build()
    runs, calibration = [], None
    if args.command == 'ddr-add-test':
        for config in [dict(elements=4099), dict(elements=1027, passes=2, latency=7, stall=3),
                       dict(elements=67, inject=True, expected_failure='mismatch'),
                       dict(elements=67, max_cycles=20, expected_failure='timeout')]:
            path, _ = application(**config)
            runs.append(str(path.relative_to(ROOT)))
    else:
        if args.target_seconds:
            print('CALIBRATION: time two complete passes with the same data size and DDR settings.', flush=True)
            sample_path, sample = application(elements, passes=2, latency=args.latency,
                                               stall=args.stall, timeout=timeout)
            runs.append(str(sample_path.relative_to(ROOT)))
            seconds_per_pass = sample['simulator_wall_seconds']/2
            if seconds_per_pass <= 0: raise RuntimeError('Calibration duration too small to measure')
            passes = max(1, round(args.target_seconds/seconds_per_pass))
            if passes > 100000: raise RuntimeError('Too many calibrated passes; increase --elements')
            calibration = dict(target_seconds=args.target_seconds, seconds_per_pass=seconds_per_pass,
                               chosen_passes=passes, projected_seconds=seconds_per_pass*passes)
            print(f'CALIBRATED: {seconds_per_pass:.2f} s/pass -> {passes} passes, '
                  f'about {seconds_per_pass*passes/60:.1f} minutes. This is an estimate, not a deadline.', flush=True)
        path, _ = application(elements, passes, args.latency, args.stall, args.inject_failure,
                              timeout, args.max_cycles)
        runs.append(str(path.relative_to(ROOT)))
    dest = run_dir('ddr-add-summary')
    (dest/'result.json').write_text(json.dumps(dict(result='PASS', runs=runs,
        calibration=calibration, full_4gib_sweep=False), indent=2)+'\n')
    print('DDR ADD SUMMARY:', dest, flush=True)


if __name__ == '__main__':
    try: main()
    except KeyboardInterrupt:
        print('\nDDR ADD interrupted; simulator stopped.', file=sys.stderr)
        sys.exit(130)
    except Exception as error:
        print('DDR ADD FAIL: '+str(error), file=sys.stderr)
        sys.exit(1)
