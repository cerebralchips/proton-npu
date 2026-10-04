# Matrix v1 contract

This is a custom bare-metal extension of the Proton NPU scalar and two-lane vector system.
It is not the RISC-V VME instruction set. Linux, IREE, DMA, interrupts, context
switching, floating point and output requantization are outside this milestone.

## Arithmetic and storage

The open-source integer mesh contains 4×4 processing elements.
Each PE computes four signed INT8 products plus an INT32 partial sum. Matrix v1
always uses this INT8 mode. An operation performs
`C[4][4] += A[4][16] × transpose(BT[4][16])`, modulo 2^32.
Software pads incomplete M/N/K tiles with zeros and splits K into chunks of 16.
Results are row-major INT32; there is no implicit saturation or narrowing.

This is a packed-dot-product systolic mesh. Mesh rows represent successive
groups of four K elements. A travels horizontally; partial sums travel vertically.
Ten advances fill, compute and drain one output tile. A final capture cycle
writes the last result before completion. Bus transfers are additional cycles.

## Interface

The AXI target occupies `0xE0000000..0xE0000FFF`, uncached and non-idempotent.
Its local data bus is 64 bits, little endian, with byte write enables.

| Offset | Meaning |
|---|---|
| 0x000 | Read-only identification `0x000104104D415431` |
| 0x008 | Read-only busy bit |
| 0x010 | Read-only accepted operation counters: zero low32, macc high32 |
| 0x100–0x13F | A: four rows of sixteen signed bytes |
| 0x140–0x17F | BT: four columns of B, each sixteen signed bytes |
| 0x180–0x1BF | C: sixteen row-major 32-bit values |

Reserved accesses and writes to read-only locations return a slave error.
Tile register transfers wait while the engine is active. Reset cancels an active
command, clears operands/results/counters, and resets the mesh pipeline.

Two custom-1 R-format instructions have funct3=0, rs1=rs2=x0 and an integer rd:
`mzero` (funct7=0) clears C; `mmacc` (funct7=1) accumulates a tile. The destination
receives zero on completion. Reserved encodings trap. GNU/LLVM `.insn` emits these
instructions, so a compiler fork is unnecessary for v1. Matrix instructions
do not require or dirty mstatus.VS.

Instructions enter CVA6's accelerator dispatch path and must reach retirement
slot 0 before dispatch. Waiting for slot 0 prevents an older fence from flushing
and replaying a command that has already modified matrix state. Custom-0 remains
assigned to this CVA6 fork's FENCE.T; matrix v1 uses custom-1 (0x2B).

Matrix instructions serialize younger issue. In the matrix-enabled configuration,
RVV requests also wait for retirement slot 0, and vector memory tracking counts
accepted requests (valid AND ready). These conservative rules favor correctness
over issue throughput. The router waits for older Ara work and scalar stores to
drain, routes the command, and returns completion with the original scoreboard
transaction ID. Ara memory-completion, FP flags, MMU and cache-invalidation
sidebands continue flowing while the matrix command waits. The C API also uses
compiler memory barriers and architectural fences.

The single-hart bare-metal software owns the tile buffers. Operands/results use
scalar MMIO copies; RVV operates on normal RAM before/after those copies.

## Verification gates

1. Preserve and run the existing scalar/vector regression.
2. Exhaust signed byte pairs in every packed PE lane; check INT32 wraparound.
3. Compare full tile RTL against an independent conventional Python i/j/k oracle,
   including padded K, negative/extreme inputs and nonzero accumulator seeds.
4. Check register decode, byte strobes, reset during work and bounded completion.
5. Check AXI channel backpressure, errors and command/transfer arbitration.
6. Check custom instruction routing, transaction IDs, ordering and wrong-path safety.
7. Run one ELF with scalar, RVV and custom matrix instructions and compare every
   output against independently computed references, including multi-tile tails.
8. Retain decoded instruction evidence, FST, hashes, logs and regressions; inject
   bad results/timeouts to confirm the runner rejects them.

Passing these gates establishes functional correctness for the tested v1 contract.
It is not complete ISA conformance, formal verification or physical timing closure.

## Practical boundary

This is an INT8 compute prototype, not a Linux application-core sign-off. The
custom tile state has no context-switch protocol or Linux driver. The software
owns the device exclusively, and the workload runs in M mode through upstream's
`rvtest_init` hook. The baseline runtime otherwise enters U mode. Matrix v1 is
restricted to the tested two-lane/64-bit AXI configuration; other lane counts
fail elaboration explicitly. There is no claim of DMA coherency, interrupt
handling, multi-hart safety, area/frequency, or speedup over Ara.

The full unmodified Quadrilatero coprocessor is not instantiated: this project
reuses its three compute RTL files and adds our local buffers, controller, AXI
target, command router and CPU integration. Provenance and source hashes are in
`hardware/matrix/vendor/quadrilatero/provenance.json`. The integer mesh is
configured with FPU=0 and ENABLE_SIMD=1.

---

**[Cerebral Chips](https://www.cerebralchips.com) · Proton NPU**

Every machine should think.
