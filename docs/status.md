# Proton NPU status

The current bare-metal **scalar + vector + matrix** milestone is operational in
Verilator. One ELF executes scalar, RVV and custom matrix instructions on the
actual CPU model. The initial functional results below were measured on
3 October 2026. See [portable verification records](../verification/README.md)
for JSON/CSV evidence, source hashes and commands to reproduce it.

| Gate | Result |
| --- | --- |
| Integer PE | 262,144 signed-byte/lane combinations, including accumulator wraparound |
| Tile | 256 independently calculated cases, padded K and arbitrary accumulator seeds |
| Bus/controller/router | Byte enables, errors, AW/W skew, response backpressure, reset, ordering, transaction IDs |
| Combined ELF | Eight shapes including 5×7×19 and 9×5×33 tails; 115,650 RTL cycles |
| Retirement | 69,007 scalar + 64 vector + 52 mzero + 34 mmacc |
| Command reconciliation | 86 matching issue/done/response sequences |
| Actual FST tile checks | All 86 output tiles match; ten pump advances per mmacc |
| Matrix-enabled regression | 9/9 selected scalar/vector tests |
| Matrix-disabled regression | 9/9; preserved baseline cycle counts |
| Failure gates | Wrong result and forced 20-cycle timeout rejected |

Integration guards resolved custom-0's collision with CVA6 FENCE.T, retirement
slot-1 replay after an older fence, and valid-only vector memory accounting under
backpressure. The matrix configuration uses custom-1, slot-0 dispatch and
valid/ready accounting. The baseline remains selectable. The application also
checks reserved encodings, VS-off matrix execution, a branch over a matrix
instruction, and 32 unfenced store/command/load sequences.

## Scalar/vector baseline

Upstream hello-world passed on RTL and Spike (1,180 RTL cycles). The scalar/vector
C demo passed ten lengths, 0 through 257, in 57,632 RTL cycles with matching Spike
application results. Its tracing build reports the same count. The regression
includes scalar add/multiply, vector configuration, add/multiply/reduction,
32-bit load/store and vector floating-point add.

## Optional SRAM + DDR simulation — 6 October 2026

The separate `PROTON_DDR` target passed functional verification with **16 MiB
SRAM and 4 GiB external memory**. `./scripts/ara ddr-test` runs the AXI unit gate,
six invalid-ELF rejection checks, high-address ELF preload checks, and the
bare-metal scalar/vector memory test at two response-delay settings. It also
runs the existing combined scalar/vector/matrix ELF on this target.

The final bare-metal runs took **281,762 cycles** (latency 1/stall 0) and
**384,130 cycles** (latency 7/stall 3). The actual FST independently verified
**8,637 reads and 8,428 writes**, all 4,096 MiB regions, every byte-enable lane,
and three unmapped read plus three unmapped write `DECERR` responses. The combined
matrix ELF retained **115,650 cycles**. Both existing nine-test regressions and
the matrix negative gates passed.

This samples the full address range; it does not sweep every byte. The external
memory is an uncached behavioral model, not a DDR PHY or physical timing model.
The pinned CPU does not turn ordinary AXI errors into architectural access
exceptions; boundary checks verify the AXI responses directly. SDK deployment
and its numerical qualification are maintained separately in
[proton-sdk](https://github.com/cerebralchips/proton-sdk/blob/main/docs/ddr.md). See the [run guide](ddr-simulation.md),
[measured record](../verification/2026-10-06/ddr.json) and
[waveform checks](../verification/2026-10-06/ddr-waveform.json).

### Dense DDR transfer checks

`./scripts/ara ddr-sweep-smoke` additionally passes both **DDR → DDR** and
**DDR → SRAM → DDR** vector transfer tests. Each mode checks every output word
in 64 KiB + 24-byte ranges at both ends of DDR, plus a 256 KiB + 24-byte range.
The SRAM test reuses 4 KiB buffers at the low/high ends of the reserved staging
area, including a short final chunk. Delayed high-address FSTs each independently
verify **16,391 reads and 16,391 writes**, including guards, with exactly two
reads/writes per selected data word. Both deliberate-corruption checks pass.

The larger untraced runs took **915,662 cycles / 21.99 seconds** (direct) and
**1,429,172 cycles / 33.62 seconds** (staged). Linear projection gives about
**99 and 152 hours**, respectively, for 4 GiB at latency 1/stall 0; these are
estimates, not measured full sweeps. Full occupancy of the current associative
word backend exceeds the standard VM's host RAM. Full mode defaults to a 14 MiB
SRAM buffer, reserving 2 MiB for code/data/stack.

An optional vector input-generation sequence stalled after two stores and remains
unresolved. The passing transfer tests initialize with scalar stores and use
vector loads/stores for the tested transfers, with independent scalar readback.
The failure is retained through `--vector-init`; this result does not qualify that
producer sequence or all-byte 4 GiB execution. See the
[dense sweep record](../verification/2026-10-06/ddr-sweeps.json) and
[commands and limitations](ddr-simulation.md#dense-vector-sweeps).

### Timed DDR/SRAM vector-add exercise

`./scripts/ara ddr-add` adds two 32-bit buffers using **DDR → SRAM → vector add →
SRAM → DDR**, with scalar verification of every output, unchanged input checks,
and guards around buffers. Explicit `vle32.v`, `vse32.v` and `vadd.vv` are present
in the ELF. The initial 4,099-element run passed in **290,915 cycles / 6.38 seconds**
of simulator wall time. Delayed DDR (latency 7/stall 3), repeated passes, a
deliberately corrupted output and a forced timeout passed their respective gates.

The 60-second calibration experiment selected ten passes and completed in
**60.28 simulator seconds / 2,730,735 cycles**, checking 40,990 outputs. The outer
Mac command took 75.81 seconds including calibration and compilation. The runner
streams progress and uses Linux `/usr/bin/time -p` for simulator-only timing.
`--target-seconds 3600` calibrates an approximately one-hour workload with a small
fixed memory footprint and changing inputs; a complete hour was not run during
these checks. It does not sweep all 4 GiB. Waveform and instruction dumps are
disabled for these timing runs. See the [instructions](ddr-simulation.md#try-a-timed-ddr--sram--vector-addition--ddr-program)
and [verification record](../verification/2026-10-06/ddr-vector-add.json).

## Scope and limits

This is functional RTL validation of the [matrix contract](matrix-design.md),
not full ISA conformance, formal verification, Linux support, timing closure or
measured AI speedup. Simulation ticks are not a physical clock specification.
The [PE explorer](pe-array-explorer.html) is a separate teaching model and is not
RTL proof. The Linux guest runs build tools; it is not Linux running on Proton NPU.

The supported build profile is ARM64 Ubuntu 24.04, tested in Lima on Apple Silicon.
See [environment notes](environment.md) for exact source/tool choices and the
remaining validation limit of the new clean-install bootstrap. Original runs
reuse the validated GCC/Newlib runtime, while a clean checkout can build it.

---

**[Cerebral Chips](https://www.cerebralchips.com) · Proton NPU**

Every machine should think.

## Optional programmable DMA — 7 October 2026

The `PROTON_DMA` configuration adds a separate AXI master and registers at
`0xe0001000` for SRAM ↔ DDR copy and transpose. It supports 64-bit physical
addresses, 8/16/32/64-bit elements and independent row strides. It is single
channel, polled and noncoherent; the qualified bare-metal policy disables the
CPU data cache and fences transfer-buffer ownership.

All 80 unit checks and 21 CPU-driven transfer cases passed, plus six invalid
descriptors. Normal and delayed runs took **459,863** and **495,473 cycles**.
The actual FST independently verified **257 reads and 257 writes**, their
addresses/data/strobes, transpose layout, completion ordering, and final DDR byte.
The payload totals 945 bytes across directed cases; this is not a capacity sweep.

The combined scalar/vector/matrix workload still passes in **115,650 cycles**
on the DMA configuration, including its actual matrix tile waveform. Both
nine-test regressions, matrix failure gates and the existing DDR suite passed.
Corrupt DMA waveform expectations and a forced timeout were rejected.

See the [DMA design and run guide](dma.md),
[measured evidence](../verification/2026-10-07/dma.json), and
[waveform checks](../verification/2026-10-07/dma-waveform.json). SDK DMA integration,
cache-coherent operation, bursts, interrupts and physical implementation remain
outside this qualification.
