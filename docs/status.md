# Proton NPU status

The current bare-metal **CVA6 + Ara + matrix** milestone is operational in
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
