# Running scalar + vector + matrix RTL

Run these from the Mac, inside `proton-npu`. The shared Lima VM must be running.
The first build takes longer; later runs reuse the compiled simulator.

```bash
cd proton-npu
./scripts/ara vm-start
./scripts/ara matrix-unit
./scripts/ara matrix
./scripts/ara matrix-wave
```

`matrix-unit` checks the real integer MAC, mesh/controller, AXI-Lite target and
command router. `matrix` repeats those gates, applies reviewed dependency
patches, builds the separate `build-matrix` model, compiles one RISC-V ELF, and
runs it on CVA6 + Ara + matrix RTL. A failed gate stops the command.

The program is [main.c](../examples/scalar_vector_matrix/main.c), with the
[matrix C API](../examples/scalar_vector_matrix/matrix.h) and
[tiling library](../examples/scalar_vector_matrix/matrix.c). LLVM emits RVV
instructions from intrinsics and custom matrix instructions through `.insn`.
The library packs four A rows and four transposed B columns into local buffers,
zero-pads tails, accumulates K in chunks of sixteen and copies INT32 results out.

The workload performs scalar setup, RVV input addition, hardware matrix multiply,
RVV output addition, then scalar checks against both a C calculation and Python
generated expectations. Its eight shapes include 4×4×4, 8×8×8, 5×7×19 and 9×5×33.
Every output is checked; operation counters and buffer guards are checked too.
The ELF also tests VS-off execution, reserved instruction traps, a skipped
wrong-path command, and 32 unfenced store/instruction/load sequences.

Successful output ends with `RESULT: PASS scalar_vector_matrix cases=8`, the RTL
`*** SUCCESS ***` marker, and a positive cycle count. The runner then validates
the actual instruction and command traces. It does not run custom instructions
through unmodified Spike or call that an independent ISA implementation.

## Inspect evidence and waveforms

```bash
./scripts/ara latest matrix
./scripts/ara latest matrix-elf
code "$(./scripts/ara latest matrix-wave)"
code "$(./scripts/ara latest matrix-fst)"
```

Open `matrix.vcd` using your VS Code waveform viewer. It is extracted from the
actual FST and includes `cmd_valid`, `cmd_ready`, `cmd_macc`, `busy`, `pump`,
`step`, `done`, A/BT/C buffers, and all sixteen PEs' operands and partial sums.
Start with the first `cmd_macc=1` handshake. Follow ten `pump` advances; the final
capture precedes `done`. The full FST also contains CPU, Ara and AXI internals.
The displayed 1 ps ticks describe simulator time, not a synthesized clock rate.

| File in the successful run directory | What it establishes |
|---|---|
| `program.elf`, `program.dump` | Exact executable and compiler disassembly |
| `instructions.csv` | Retired scalar, vector and decoded custom matrix instructions with PC/cycle |
| `matrix-events.csv` | Tagged matrix issue, done and response events |
| `accelerator-dispatch.csv` | CPU issue/queue/dispatch diagnostic history, including flushed issue |
| `execution-evidence.json` | Matched instruction counts and workload checksums |
| `matrix-wave-check.json` | Each command's expected and observed tile, checked directly from FST |
| `result.json` | Gate result, source/patch/ELF/simulator hashes and cycle count |
| `rtl.log`, `compile.log` | Console results and exact build/run commands |

`instructions.csv` is a retirement trace; `accelerator-dispatch.csv` also includes
instructions that were subsequently flushed and must not be counted as execution.
An unknown mnemonic in the toolchain disassembly is expected for the custom ISA;
the evidence decoder labels the two instructions `mzero` and `mmacc`.

## Regression and deliberate failure gates

```bash
./scripts/ara matrix-smoke    # Nine upstream scalar/vector tests, matrix enabled
./scripts/ara matrix-negative # Bad result and forced timeout must be rejected
./scripts/ara smoke           # Original matrix-disabled configuration
```

The negative command intentionally retains failed application directories and
reports success only if the intended failures are rejected. A failed compile
does not qualify. Build/run operations are serialized by the VM file lock.
No Linux services, matrix compiler fork, DMA or physical-design flow is required
for this milestone. The tested contract and remaining limits are in
[matrix-design.md](matrix-design.md).
