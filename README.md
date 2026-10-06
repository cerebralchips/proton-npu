# Proton NPU

**[Cerebral Chips](https://www.cerebralchips.com) · Every machine should think.**

Proton NPU is our open hardware platform for scalar, vector and matrix computing.
One 64-bit RISC-V core runs a single bare-metal ELF containing scalar instructions,
RVV 1.0 vector instructions, and custom instructions for a 4×4 INT8 matrix engine.
The current milestone is verified in RTL simulation on Apple Silicon through an
ARM64 Linux VM.

![Proton NPU system architecture](docs/assets/system.svg)

[Company website](https://www.cerebralchips.com) ·
[Architecture guide](https://cerebralchips.github.io/proton-npu/) ·
[Documentation index](docs/README.md) · [Run guide](docs/matrix-running.md) ·
[Verification records](verification/README.md) · [Contributing](CONTRIBUTING.md)

## Current hardware

| Block | Configuration |
| --- | --- |
| 64-bit RISC-V core | One RV64 application core; actual CPU pipeline enabled |
| RVV 1.0 vector unit | RVV 1.0, two lanes, VLEN 2048 bits, ELEN 64 bits |
| INT8 matrix engine | 4×4 PEs, four signed INT8 products per PE, INT32 accumulation |
| Matrix operation | `C[4][4] += A[4][16] × transpose(BT[4][16])`, modulo 2³² |
| Integration | Custom-1 `mzero` / `mmacc`; AXI-Lite mapped buffers at `0xe0000000` |
| Internal memory | 16 MiB SRAM at `0x80000000`, shared by code and working buffers |
| Optional external memory | 4 GiB functional DDR model at `0x100000000`; separate `PROTON_DDR` simulation target |
| Software | LLVM 20.1.0, RVV intrinsics and inline `.insn`; Newlib bare-metal runtime |

The matrix buffers are filled and read by CPU loads/stores. This version has no
matrix DMA or direct vector-register connection. There is no measured silicon
frequency or TOPS result. Linux, IREE, synthesis and full ISA compliance are future
milestones; see [scope and evidence](docs/status.md).

## Build and run

Supported provisioning profile: **Ubuntu 24.04 ARM64**. Apple Silicon uses Lima
with 6 virtual CPUs, 8 GiB RAM and 4 GiB swap; allow substantial disk space for
LLVM, toolchains and simulator builds. The Linux guest builds the simulator;
the RISC-V program executes on simulated RTL, not on the Mac's CPU ISA.

```bash
git clone --branch hardware https://github.com/cerebralchips/proton-npu.git
cd proton-npu
./scripts/ara vm-start       # Mac: download/check Lima and create/start the VM
./scripts/ara provision      # Install pinned tools, dependencies and patches
./scripts/ara doctor         # Inspect source pins, tools and configuration
./scripts/ara matrix         # Unit gates + compile + run the combined ELF
```

On ARM64 Ubuntu, skip `vm-start`. Initial provisioning/building is lengthy;
subsequent commands reuse tools and simulators. See [environment notes](docs/environment.md)
for overrides, runtime selection and the validation limits of the fresh setup path.
Run only one build/simulation at a time; the launcher enforces a guest lock.

```bash
./scripts/ara hello          # Scalar hello-world on the CPU + vector system
./scripts/ara run            # Scalar + vector C example, compared with Spike
./scripts/ara matrix-wave    # Combined ELF, FST capture and independent tile checks
./scripts/ara latest matrix-wave
./scripts/ara latest matrix-fst
./scripts/ara matrix-smoke   # Nine selected scalar/vector regression tests
./scripts/ara matrix-negative # Ensure wrong results and timeouts are rejected
./scripts/ara smoke          # Matrix-disabled baseline regression
./scripts/ara ddr-test       # Optional 16 MiB SRAM + 4 GiB functional DDR target
./scripts/ara ddr-sweep-smoke # Dense vector DDR and DDR/SRAM/DDR checks on bounded ranges
./scripts/ara ddr-add         # Live DDR -> SRAM -> vector addition -> DDR, with PASS/FAIL
```

Open the generated FST or extracted `matrix.vcd` in a waveform viewer. Retired
instructions and tagged command events are exported as CSV beside the waveform.
The [waveform guide](docs/waveforms.md) and [matrix run guide](docs/matrix-running.md)
explain these files.

The [DDR simulation guide](docs/ddr-simulation.md) describes the separate memory
map, bare-metal checks and independently checked external-memory traces. This
target models external memory functionally; it does not implement a DDR PHY.
The [Proton SDK](https://github.com/cerebralchips/proton-sdk) owns IREE/model
deployment, weight placement and numerical model validation. Its DDR profile
places packed INT8 weights in external memory and working buffers in SRAM; see
the [SDK reproduction guide](https://github.com/cerebralchips/proton-sdk/blob/main/docs/reproduce.md)
for the qualified hardware revision and commands.
The guide also includes a [timed vector-add exercise](docs/ddr-simulation.md#try-a-timed-ddr--sram--vector-addition--ddr-program)
with a small example and an automatically calibrated, approximately one-hour run.

## Verification baseline

The published baseline passes eight combined workloads in **115,650 RTL cycles**:
69,007 scalar, 64 vector, 52 `mzero` and 34 `mmacc` retired instructions. All 86 matrix
commands reconcile with completion events and independently checked waveform tiles.
Standalone gates cover 262,144 signed-byte/lane combinations, 256 tile cases,
bus backpressure/errors and router ordering. Both selected regression suites pass 9/9.

These are functional simulation results, not timing closure or measured AI throughput.
Small, source-linked records are in [verification/](verification/README.md).
Full logs, ELFs and waveforms are regenerated locally under ignored `artifacts/`.

## Repository layout

| Path | Purpose |
| --- | --- |
| `hardware/matrix/` | Matrix controller, buffers, router and pinned compute RTL |
| `hardware/memory/` | Optional sparse external-memory model for Verilator |
| `patches/ara/`, `patches/cva6/` | Reproducible integration and build changes |
| `examples/` | Bare-metal scalar/vector and scalar/vector/matrix applications |
| `tests/matrix/` | Independent arithmetic oracle and RTL testbenches |
| `scripts/` | Provisioning, serial execution, tracing and evidence checks |
| `docs/` | Offline HTML architecture guide, SVG diagrams and technical notes |
| `verification/` | Portable verification snapshots |
| `sources.lock.json` | Upstream revisions and release checksums |

The scalar and vector IPs are fetched at matched revisions into ignored `upstream/`; they are
not copied wholesale into this repository. `provision` reconstructs the source
assembly from the lock and reviewable patches. Agent guidance is in [AGENTS.md](AGENTS.md).

## License and credits

Cerebral Chips' original contributions use [Apache-2.0](LICENSE). Third-party IP,
adaptations and patches retain their applicable licenses. See [THIRD_PARTY.md](THIRD_PARTY.md)
for upstream hardware, runtime and tool attribution. Upstream licenses and
copyright notices are preserved; the root license does not replace them.

---

**[Cerebral Chips](https://www.cerebralchips.com) · Proton NPU**

Every machine should think.
