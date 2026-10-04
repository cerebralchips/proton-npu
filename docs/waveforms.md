# Waveform lesson: follow vector instructions into register writes

Generate and open the small teaching waveform from the Mac:

```bash
cd proton-npu
./scripts/ara wave
code "$(./scripts/ara latest wave)"
```

In VS Code, use **Reopen Editor With → Surfer Waveform Viewer** if needed.
Expand `lesson` in the scope tree and add signals from the list below. Zoom to
fit once, then zoom into the example windows. Opening a file does not automatically
add signals to the waveform pane.

The `wave` command creates the original `sim.fst`, a filtered `lesson.vcd`,
`commit-port0.csv`, `vector-lane-writes.csv`, and `wave-summary.json`. The latter
contains full original signal paths. The CSVs open in any text editor or spreadsheet.

```bash
code "$(./scripts/ara latest fst)"     # Full hardware hierarchy
RUN=$(./scripts/ara latest run)
code "$RUN/commit-port0.csv"
code "$RUN/vector-lane-writes.csv"
```

FST is a compact binary signal history; VCD is a text signal history. Both show
signal values over simulated time. Our VCD is generated from selected signals
in the FST, so both describe the same execution. Neither format inherently knows
C variables or assembly mnemonics. The lesson exporter combines sampled CPU PCs
with the ELF disassembly to produce the annotated instruction CSV.

## Begin with these signals

| Signal under `lesson` | What to look for |
| --- | --- |
| `clk`, `rst_n` | Clock edges and release from reset |
| `pc_commit0`, `commit_ack` | Address of the first commit slot; bit 0 of acknowledgement indicates a valid commit |
| `vl`, `vtype` | Active element count and encoded element-width/register-group configuration |
| `vector_req_valid`, `vector_req_ready` | Both high indicate a vector backend request can transfer at the rising edge |
| `lane0_req`, `lane0_gnt`, `lane0_data` | Lane 0 ALU result transfer |
| `lane1_req`, `lane1_gnt`, `lane1_data` | Lane 1 ALU result transfer |
| `lane0_address`, `lane1_address` | Vector register file word addresses |
| `lane0_byte_enable`, `lane1_byte_enable` | Which bytes of the 64-bit word are actually written |
| `scalar_write_enable`, `scalar_destinations`, `scalar_write_data` | Packed two-port scalar register writes; port 0 occupies the low bits |
| `exit` | Program termination; successful encoded exit is 1 |

Use hexadecimal for PC and packed data. Decimal is useful for `vl` and addresses.
Only interpret a data bus when its corresponding valid/enable condition is true.

## Concrete example: seven numbers

These observations were decoded from the
locally generated waveform (`./scripts/ara latest fst`).
The trace uses 1 ps ticks and a two-tick clock period. This is a simulation time
convention, not the frequency of a physical CPU. Source or compiler changes can
move the timestamps and PCs; regenerate the tables for each new build.

First zoom to approximately **28,600–28,720 ps** (28.600–28.720 ns).
The C example computes `[1, 4, 7, 10, 13, 16, 19]` in this window.

| Sample time (ps) | PC | Instruction / observation |
| --- | --- | --- |
| 28,618 | `0x80000300` | `vsetvli`: active length becomes 7; scalar register `x14` receives 7 |
| 28,630 | `0x80000304` | `vle32.v v8, (a3)`: load A |
| 28,642 | `0x80000308` | `vle32.v v9, (a2)`: load B |
| 28,652 | `0x80000316` | `vadd.vv v8, v8, v9`: vector addition |
| 28,664 | `0x8000031a` | `vse32.v v8, (a1)`: store C |
| 28,670 | — | Lane 0 result word holds 1 and 7; lane 1 holds 4 and 10 |
| 28,672 | — | Lane 0 holds 13 and 19; lane 1 writes 16 using only the low four bytes |

The result data is distributed across lanes. For example,
`lane0_data = 0x0000000700000001` contains two 32-bit results: 1 in the low half
and 7 in the high half. The adjacent element 4 is in lane 1. The lane word address
128 is the beginning of vector register v8 in this two-lane configuration
(`vaddr = register_number * 16`). Address 129 is its next word.

Notice that the vector instruction appears in the CPU commit stream before the
ALU result transfer. Ara's instruction acknowledgement and completion of every
element are distinct events. The vector store waits for the required data.

Next zoom to **32,490–32,600 ps**:

- At sample 32,524, `vredsum.vs v8, v8, v9` performs the reduction.
- At 32,566, lane 0's enabled low four bytes contain `0x46`, decimal **70**.
- At 32,574, `vmv.x.s a1, v8` returns the result to scalar register **x11/a1**.

The high half of a result bus can contain other bits even when disabled. For
the final reduction, byte enable `0x0f` means only the low 32 bits are written.

## Limits of the teaching tables

The exporter records **falling-edge snapshots**: the displayed handshake values
are stable before the following rising edge. The CPU CSV covers **commit port 0
only**, and the lane CSV covers ALU result transfers, not all vector loads or
every write to the vector register file. These are selected observations for
learning, not a complete architectural trace or a reference-model comparison.

The baseline exporter observed 216 vector instruction samples in the two teaching
functions, with 250 lane-0 and 210 lane-1 ALU result transfers. The full FST contains
53,214 declared signals and is about 34 MB; the filtered VCD is about 11 MB.

Full paths can be enumerated in Linux with:

```bash
./scripts/ara shell
source scripts/lab/env.sh
python3 scripts/lab/wave-signals.py "$(python3 scripts/lab/latest.py fst)"
```

Wave content and exported tables were checked programmatically. Surfer is installed
in the existing VS Code setup; its GUI interaction was not automated here.
