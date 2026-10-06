#!/usr/bin/env python3
"""Reconstruct DDR contents independently from actual Verilator FST handshakes."""
import csv
import argparse
from collections import defaultdict, deque
import json
from pathlib import Path
import subprocess
import sys
import struct

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('wave', type=Path)
parser.add_argument('--sweep', type=Path, help='Dense sweep run manifest; replaces sampled-test coverage gates')
args = parser.parse_args()
wave = args.wave
sweep = json.loads(args.sweep.read_text()) if args.sweep else None
word_reads, word_writes = defaultdict(int), defaultdict(int)
root = wave.parent
prefix = 'TOP.ara_tb_verilator.dut.i_ara_soc.i_ddr.'
paths = {'clk': 'TOP.clk_i', 'reset': 'TOP.rst_ni'}
for name in ['mem_req', 'mem_gnt', 'mem_we', 'mem_addr', 'mem_wdata', 'mem_strb',
             'mem_rvalid', 'mem_rdata', 'mem_error', 'latency', 'stall_cycles']:
    paths[name] = prefix + name
for name in ['ar_valid','ar_ready','ar_addr','ar_id','ar_len','r_valid','r_ready',
             'r_id','r_resp','r_last','aw_valid','aw_ready','aw_addr','aw_id',
             'b_valid','b_ready','b_id','b_resp']:
    paths[name] = 'TOP.ara_tb_verilator.dut.i_ara_soc.ddr_check_' + name
process = subprocess.Popen(['fst2vcd', str(wave)], stdout=subprocess.PIPE, text=True,
                           bufsize=1024*1024)
scope, signals = [], {}
wanted = {path: name for name, path in paths.items()}
for line in process.stdout:
    parts = line.split()
    if not parts: continue
    if parts[0] == '$scope': scope.append(parts[2])
    elif parts[0] == '$upscope': scope.pop()
    elif parts[0] == '$var':
        path = '.'.join([*scope, parts[4]])
        if path in wanted:
            signals[wanted[path]] = {'id': parts[3], 'width': int(parts[2]), 'path': path}
    elif parts[0] == '$enddefinitions': break
if set(paths) != set(signals):
    process.terminate(); process.wait()
    raise SystemExit('Missing DDR waveform signals: ' + str(set(paths)-set(signals)))
selected = {s['id'] for s in signals.values()}
state, memory, pending = {}, {}, None
# Seed the independent oracle from the actual external ELF input, if provided.
preload = root/'ddr-preload.elf'
if preload.exists():
    raw = preload.read_bytes()
    phoff = struct.unpack_from('<Q', raw, 32)[0]
    phsize, phnum = struct.unpack_from('<HH', raw, 54)
    for index in range(phnum):
        kind, flags, offset, va, address, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ', raw, phoff+index*phsize)
        if kind == 1:
            if filesz != 8 or memsz != 8 or address % 8: raise RuntimeError('Unexpected preload segment')
            memory[address] = struct.unpack_from('<Q', raw, offset)[0]
time, cycles, reads, writes, stalls = 0, 0, 0, 0, 0
min_address, max_address = 2**64-1, 0
latencies, touched_mib, byte_masks = set(), set(), set()
axi_reads, axi_writes = defaultdict(deque), defaultdict(deque)
boundary_addresses = {0x81000000, 0xfffffff8, 0x200000000}
read_errors, write_errors = [], []
axi_read_beats, axi_write_responses = 0, 0
csvfile = (root/'ddr-transactions.csv').open('w')
writer = csv.writer(csvfile)
writer.writerow(['request_cycle', 'response_cycle', 'address', 'write', 'strobe', 'write_data', 'read_data', 'error'])
vcd = (root/'ddr.vcd').open('w')
vcd.write('$timescale 1ps $end\n$scope module ddr $end\n')
for name, signal in signals.items():
    vcd.write(f'$var wire {signal["width"]} {signal["id"]} {name} $end\n')
vcd.write('$upscope $end\n$enddefinitions $end\n')

def value(name):
    bits = state.get(signals[name]['id'], '0')
    if any(c in bits for c in 'xXzZ'): raise RuntimeError(f'Unknown {name} at {time}')
    return int(bits, 2)

def sample():
    global pending, cycles, reads, writes, stalls, min_address, max_address
    global axi_read_beats, axi_write_responses
    # At falling edges these are the stable signals for the following rising edge.
    if value('clk') or not value('reset'): return
    cycles += 1
    if value('ar_valid') and value('ar_ready'):
        axi_reads[value('ar_id')].append([value('ar_addr'), value('ar_len')+1])
    if value('aw_valid') and value('aw_ready'):
        axi_writes[value('aw_id')].append(value('aw_addr'))
    if value('r_valid') and value('r_ready'):
        queue = axi_reads[value('r_id')]
        if not queue: raise RuntimeError('AXI read response without matching ID/request')
        address, beats = queue[0]
        expected_resp = 3 if address in boundary_addresses else 0
        if value('r_resp') != expected_resp or bool(value('r_last')) != (beats == 1):
            raise RuntimeError(f'Incorrect AXI R response/last at {address:#x}')
        if expected_resp: read_errors.append(hex(address))
        axi_read_beats += 1
        if beats == 1: queue.popleft()
        else: queue[0][1] -= 1
    if value('b_valid') and value('b_ready'):
        queue = axi_writes[value('b_id')]
        if not queue: raise RuntimeError('AXI write response without matching ID/request')
        address = queue.popleft()
        expected_resp = 3 if address in boundary_addresses else 0
        if value('b_resp') != expected_resp:
            raise RuntimeError(f'Incorrect AXI B response at {address:#x}')
        if expected_resp: write_errors.append(hex(address))
        axi_write_responses += 1
    if value('mem_rvalid'):
        if pending is None: raise RuntimeError('Memory response without accepted request')
        latency = cycles - pending['cycle']
        if latency != value('latency') + 1:
            raise RuntimeError(f'Unexpected response latency {latency}')
        latencies.add(latency)
        if value('mem_error') != pending['error']:
            raise RuntimeError('Incorrect memory error response')
        actual = value('mem_rdata')
        if not pending['we'] and not pending['error'] and actual != pending['expected']:
            raise RuntimeError(f'DDR read mismatch at {pending["address"]:#x}: {actual:#x} != {pending["expected"]:#x}')
        writer.writerow([pending['cycle'], cycles, hex(pending['address']), pending['we'],
                         hex(pending['strb']), hex(pending['data']), hex(actual), value('mem_error')])
        pending = None
    if value('mem_req') and not value('mem_gnt'): stalls += 1
    if value('mem_req') and value('mem_gnt'):
        if pending is not None: raise RuntimeError('Overlapping memory requests')
        address, data, mask, write = (value(n) for n in ['mem_addr','mem_wdata','mem_strb','mem_we'])
        error = int(not 0x100000000 <= address < 0x200000000)
        index = address & ~7
        expected = memory.get(index, 0)
        pending = {'cycle': cycles, 'address': address, 'we': write, 'strb': mask,
                   'data': data, 'expected': expected, 'error': error}
        if not error:
            if sweep:
                start = int(sweep['ddr_start'], 16)
                end = start + sweep['bytes']
                if start <= address < end:
                    if address % 8: raise RuntimeError('Unaligned dense sweep beat')
                    if write:
                        # Independent host formula checks initialization and vector stores,
                        # not just agreement between the model's reads and writes.
                        expected_data = (address >> 3) ^ 0xd3c5a709abcd1234
                        if word_writes[address] == 1: expected_data ^= 0x96a53cc3f00f5aa5
                        if mask != 255 or data != expected_data or word_writes[address] >= 2:
                            raise RuntimeError(f'Incorrect dense vector write at {address:#x}')
                        word_writes[address] += 1
                    else: word_reads[address] += 1
                elif address not in {start-8, end}:
                    raise RuntimeError(f'DDR access outside selected range/guards: {address:#x}')
            min_address = min(min_address, address); max_address = max(max_address, address)
            touched_mib.add((address-0x100000000) >> 20)
            if write:
                writes += 1; byte_masks.add(mask)
                for byte in range(8):
                    if mask & (1 << byte):
                        expected = (expected & ~(255 << (8*byte))) | (data & (255 << (8*byte)))
                memory[index] = expected
            else: reads += 1

try:
    for line in process.stdout:
        if line.startswith('#'):
            sample(); time = int(line[1:]); vcd.write(line)
        elif line[0] in '01xXzZ':
            code = line[1:].strip()
            if code in selected: state[code] = line[0]; vcd.write(line)
        elif line[0] in 'bB':
            bits, code = line[1:].split()
            if code in selected: state[code] = bits; vcd.write(line)
    sample()
finally:
    vcd.close(); csvfile.close(); process.stdout.close()
if process.wait() != 0: raise SystemExit('FST conversion failed')
def is_ddr(address):
    return 0x100000000 <= address < 0x200000000 or address in boundary_addresses

# These AXI signals are on the shared system port: instruction fetches and the
# final completion MMIO write can still be pending when the simulator stops.
if (pending is not None or any(is_ddr(a) for q in axi_reads.values() for a, _ in q) or
        any(is_ddr(a) for q in axi_writes.values() for a in q)):
    raise SystemExit('Outstanding DDR request at end of waveform')
if value('stall_cycles') and not stalls: raise SystemExit('No backpressure observed')
if sweep:
    nwords = sweep['bytes']//8
    if (len(word_reads) != nwords or len(word_writes) != nwords or
            set(word_reads.values()) != {2} or set(word_writes.values()) != {2}):
        raise SystemExit('Dense sweep did not read/write every selected word exactly twice')
    if read_errors or write_errors: raise SystemExit('Unexpected AXI error in dense sweep')
else:
    if reads < 8192 or writes < 8192 or len(touched_mib) != 4096:
        raise SystemExit('Incomplete DDR waveform coverage')
    if min_address != 0x100000000 or max_address < 0x1fffffff8:
        raise SystemExit('DDR endpoint coverage missing')
    if not set(1 << b for b in range(8)) <= byte_masks:
        raise SystemExit('Byte-strobe coverage missing')
    if sorted(read_errors) != sorted(map(hex, boundary_addresses)) or sorted(write_errors) != sorted(map(hex, boundary_addresses)):
        raise SystemExit('Missing exactly three boundary DECERR reads/writes')
result = {'result': 'PASS', 'reads_checked': reads, 'writes_checked': writes,
          'touched_mib_regions': len(touched_mib), 'min_address': hex(min_address),
          'max_address': hex(max_address), 'memory_response_cycles': sorted(latencies),
          'request_backpressure_cycles': stalls, 'byte_strobes': sorted(byte_masks),
          'axi_read_beats': axi_read_beats, 'axi_write_responses': axi_write_responses,
          'boundary_read_decerr': read_errors, 'boundary_write_decerr': write_errors,
          'signals': signals, 'exhaustive_byte_sweep': False}
if sweep:
    result.update(dense_bytes_checked=sweep['bytes'], mode=sweep['mode'],
                  per_word_reads=2, per_word_writes=2, independent_write_pattern_checked=True,
                  exhaustive_byte_sweep=sweep['bytes'] == 1 << 32 and sweep['offset'] == 0)
(root/'ddr-wave-check.json').write_text(json.dumps(result, indent=2)+'\n')
print(f'DDR WAVEFORM PASS: {reads} reads, {writes} writes independently checked; {len(touched_mib)} MiB regions')
