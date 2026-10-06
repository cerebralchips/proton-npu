# Programmable SRAM ↔ DDR DMA

The optional `PROTON_DMA` target adds a CPU-programmable DMA channel to the
16 MiB SRAM + 4 GiB functional DDR system. The DMA has its own AXI master port;
it moves data without the CPU performing the payload loads/stores. The CPU sets
up a transfer, starts it, and polls completion. The matrix engine remains a
separate CPU-fed AXI target; this change does not connect DMA to its tile buffers.

## Version 1 design

- One channel and one active transfer, with 64-bit physical addresses.
- Copy or transpose a row-major two-dimensional array.
- 8-, 16-, 32- or 64-bit elements. Values are copied bit for bit, without conversion.
- Independently programmable source/destination row strides in bytes.
- One single-beat read followed by one single-beat write per element. No bursts,
  descriptors, interrupts or double buffering in this first implementation.
- SRAM → DDR and DDR → SRAM only; the complete descriptor must fit the installed
  regions. Same-region/overlapping moves and MMIO destinations are rejected.
- Sticky completion/error status, confirmed byte count, and fault address.

For source shape `rows × cols` and element size `E` bytes:

```text
source address = source + row * source_stride + column * E
copy output    = destination + row * destination_stride + column * E
transpose      = destination + column * destination_stride + row * E
```

Transpose produces shape `cols × rows`. It scatters each element to its final
address as it transfers; it does not allocate a full intermediate matrix. This
simple implementation prioritizes functional correctness over bandwidth.

The state sequence is `IDLE → READ_ADDR → READ_DATA → WRITE_DATA → WRITE_RESP`.
The write address and data channels handshake independently. A transfer advances
only after a successful write response; DONE is never asserted merely because
an address or data beat was accepted. Payloads remain stable under backpressure.

## Programming interface

AXI-Lite registers start at **`0xe0001000`**, in a separate 4 KiB window next to
the matrix registers. Use aligned 64-bit register accesses. Byte write strobes
are supported at aligned register addresses; reserved/misaligned registers,
read-only writes, and all writes while busy return AXI `SLVERR`.

| Offset | Register | Contract |
| --- | --- | --- |
| `0x00` | ID, read-only | `0x00010000444d4131`: ABI 1, DMA1 |
| `0x08` | STATUS, read-only | bit 0 BUSY, bit 1 DONE, bit 2 ERROR; error code in bits 15:8 |
| `0x10` | SOURCE | 64-bit physical source address |
| `0x18` | DESTINATION | 64-bit physical destination address |
| `0x20` | SHAPE | rows in bits 15:0; columns in bits 31:16; upper bits zero |
| `0x28` | STRIDES | source row stride in bits 31:0; destination row stride in bits 63:32 |
| `0x30` | CONTROL | bit 0 START, bit 1 TRANSPOSE, bits 3:2 log2(element bytes), bit 4 CLEAR; reads zero |
| `0x38` | BYTES, read-only | Bytes whose writes received OKAY; zeroed on START/CLEAR |
| `0x40` | FAULT_ADDRESS, read-only | Source/destination of failed AXI transaction; zero for invalid descriptor |

START and CLEAR cannot be set together. Reserved control bits must be zero.
Configuration is immutable while busy; a second START is rejected. Polling reads
remain available. Each new START clears the previous result. CLEAR acknowledges
an idle result without starting a transfer.

Dimensions must be nonzero (maximum 65,535 each). Addresses and strides must be
aligned to the element size. Source stride must cover `cols * E`; destination
stride must cover `cols * E` for copy or `rows * E` for transpose. Descriptor
validation uses widened address sums to reject wrapping/out-of-range transfers
before issuing any memory access.

| Error code | Meaning |
| --- | --- |
| 1 | Invalid shape, stride, alignment, direction or memory bounds |
| 2 | Read error response or malformed read completion |
| 3 | Write error response or unexpected write response ID |

The pinned CPU does not turn ordinary AXI `SLVERR` responses into architectural
access traps. Software must program valid registers while idle and inspect DMA
STATUS; register errors are checked directly at AXI in the unit tests.

An invalid descriptor completes immediately with DONE + ERROR and zero bytes.
A bus error stops the transfer. Earlier successful writes remain visible; a
failed write may also have affected memory, so error completion is not rollback.
There is no hardware timeout/abort: if a slave never responds, software must time
out and reset the complete subsystem. Reset clears configuration and pending
state; resetting only DMA while transactions are in flight is unsupported.

## Memory ownership and caches

This DMA is **not cache coherent**. A RISC-V `fence` orders accesses but does not
invalidate cached data. The supplied M-mode example disables the pinned CVA6
write-through data cache using CSR `0x7c1` before initializing buffers and keeps
it disabled for the test. It uses `fence iorw,iorw` before START, after posting START and after
observing DONE, so configuration, memory and device accesses are ordered before
examining output. The instruction cache is unaffected.

For integration, the software must explicitly establish safe cache ownership.
The qualified policy here is to keep the data cache disabled throughout the DMA
buffer lifetime. Concurrent CPU/vector modification of transfer buffers is not
supported. The SDK's existing DDR deployment is unchanged and does not yet use
this DMA; allocator and scheduling integration are separate work.

The supported regions are SRAM `[0x80000000, 0x81000000)` and DDR
`[0x100000000, 0x200000000)`. Software must additionally avoid its own code,
stack, heap and other allocations; hardware bounds checks do not know ownership.

## Build, run and inspect

From a provisioned proton-npu checkout:

```sh
./scripts/ara dma-build
./scripts/ara dma-unit
/usr/bin/time -p ./scripts/ara dma-test
```

`dma-test` acquires the lab lock, builds `build-dma-wave`, runs the unit gates,
and executes [dma_transfer](../examples/dma_transfer/main.c) on the actual
CVA6 + Ara + matrix + DMA RTL. It runs once with DDR latency 1/stall 0 and once
with latency 7/stall 3 and FST enabled. It also runs the existing combined
scalar/vector/matrix application on the DMA-enabled configuration, checking its
matrix tile waveform as well. A corrupted
expected waveform payload and a forced simulator timeout must both be rejected.

The bare-metal program programs the registers directly and compares every
selected destination byte to an independent expected layout. It covers both
transfer directions, copy/transpose, all four element sizes, non-square and
degenerate matrices, row padding, guard bytes, high DDR addresses, and the final
DDR byte. Invalid descriptors must fail without transferring data.

The [waveform checker](../scripts/lab/dma-wave.py) extracts actual DMA AXI signals
from FST. It independently checks source/destination addresses, element sizes,
read payloads, write data/strobes, channel stability and write completions against
the test's deterministic input pattern. It also counts rejected descriptors and
observes real backpressure. The expected data is not derived from the DMA output.

Runs under `artifacts/<timestamp>-dma-*/` retain the ELF, disassembly, UART log,
instruction/event traces and result JSON. The delayed run additionally contains
an FST, a focused `dma.vcd`, `dma-transactions.csv`, and `dma-wave-check.json`.
Generated artifacts stay outside Git. To inspect only DMA in GTKWave, open
`dma.vcd`; to see the complete SoC, open the original FST.

This is functional RTL verification of the stated DMA contract. The DMA is
synthesizable RTL, but the external DDR backing model is not a controller/PHY.
FPGA/ASIC timing, physical memory integration, and formal proof are not established.

## Measured qualification — 7 October 2026

The [portable record](../verification/2026-10-07/dma.json) binds these results to
the executed source hashes and simulator binary. All gates passed:

| Gate | Result |
| --- | --- |
| DMA unit | 80 checks; copy/transpose, all byte lanes, padding, boundary validation, AW/W skew, backpressure, reset and injected bus errors |
| Bare metal, latency 1/stall 0 | 21 transfers plus six invalid descriptors; 459,863 RTL cycles |
| Bare metal, latency 7/stall 3 | Same checks; 495,473 RTL cycles; actual FST recorded |
| Independent DMA waveform | 257 reads and 257 writes; 945 payload bytes; exact addresses/data/strobes, final DDR byte, DONE ordering and byte counts |
| Failure checks | Incorrect expected payload and 20-cycle timeout rejected |
| Combined scalar/vector/matrix on DMA SoC | Eight cases, 115,650 cycles; 86 matrix commands and actual tile waveform checked |
| Existing configurations | Baseline 9/9, matrix-enabled 9/9, matrix negative gates, and DDR unit/loader/bare-metal/waveform suite passed |

The small payload intentionally tests layouts and protocol behavior, not bandwidth
or all 4 GiB. See the [waveform record](../verification/2026-10-07/dma-waveform.json)
and [decoded transactions](../verification/2026-10-07/dma-transactions.csv). The
measured cycle totals include CPU initialization, UART output and comparison;
they are not DMA-only throughput measurements.
