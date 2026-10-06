# Portable verification records

These records preserve the **3 October 2026** functional RTL milestone, before
repository publication. They were extracted from real local runs, not reconstructed
from the HTML teaching model. Original artifact identifiers and SHA-256 hashes
are in [the manifest](2026-10-03/manifest.json). Host/guest home paths are normalized
where present. Source/patch/test hashes identify the hardware under test.

| Record | Observed result |
| --- | --- |
| [Combined ELF](2026-10-03/combined-elf.json) | Eight shapes; 115,650 cycles; 69,007 scalar, 64 vector, 52 mzero, 34 mmacc retired |
| [Unit gates](2026-10-03/matrix-unit.json) | Signed integer PE, tile, bus and router tests passed |
| [Traced execution](2026-10-03/waveform-run.json) | Same workload and cycle count with waveform capture |
| [Actual RTL tile checks](2026-10-03/waveform-tiles.json) | Expected and observed INT32 values for all 86 commands; ten pumps per mmacc |
| [Command events](2026-10-03/matrix-events.csv) | Tagged issue/completion/response history |
| [Matrix regression](2026-10-03/matrix-regression.json) | 9/9 selected upstream tests |
| [Baseline regression](2026-10-03/baseline-regression.json) | 9/9 with matrix disabled; baseline cycle counts preserved |
| [Negative gates](2026-10-03/negative-gates.json) | Bad result and forced timeout rejected |
| [Patch reproduction](2026-10-03/patch-reproduction.json) | Ara patches reproduced the checked source changes |
| [Hello-world](2026-10-03/hello-world.json) | 1,180 cycles; RTL and Spike greeting/result checks |
| [Scalar/vector demo](2026-10-03/scalar-vector.json) | Ten cases; 57,632 RTL cycles; matching Spike application results |

The committed JSON/CSV records are a compact audit trail. Raw FSTs, ELFs, simulator
binaries, full instruction traces and build logs are intentionally not in Git.
Artifact IDs refer to the originating local runs, not downloadable files in this
repository. Regenerate complete evidence with:

```bash
./scripts/ara matrix
./scripts/ara matrix-wave
./scripts/ara matrix-smoke
./scripts/ara matrix-negative
./scripts/ara smoke
```

The combined ELF uses custom instructions that unmodified Spike does not implement.
It is checked by independent Python expected values, scalar C per-element checks,
retirement/command reconciliation, and direct RTL waveform inspection. Scalar/vector
Spike comparisons use separate runtime ELFs and are not lockstep comparisons.

A historical pass does not certify future edits. These checks establish functional
behavior for the documented contract, not complete ISA compliance, formal proof,
Linux readiness, physical timing or AI performance. See [status](../docs/status.md).

## Publication recheck — 4 October 2026

The final package reran the [unit gates](2026-10-04/matrix-unit.json) and
[combined ELF](2026-10-04/combined-elf.json) successfully at 115,650 cycles.
[Publication checks and source hashes](2026-10-04/publication.json) record the
setup checks and remaining limits; [browser checks](2026-10-04/browser-checks.json)
cover all six pages at desktop/mobile widths and offline opening.

## Optional SRAM + DDR target — 6 October 2026

[DDR verification](2026-10-06/ddr.json) records the source hashes, bare-metal
results, AXI unit gate, loader rejection cases, combined matrix execution and
existing regressions. [Independent FST checks](2026-10-06/ddr-waveform.json)
record 8,637 reads and 8,428 writes plus boundary AXI errors. Run
`./scripts/ara ddr-test` to reproduce. See the [DDR guide](../docs/ddr-simulation.md)
for coverage and the pinned CPU's bus-error/exception limitation.

[Dense vector sweeps](2026-10-06/ddr-sweeps.json) record both DDR → DDR and
DDR → SRAM → DDR bounded checks, independent high-address FST checks, corruption
detection, and estimated full-run costs. Reproduce with `./scripts/ara ddr-sweep-smoke`.
All-byte 4 GiB execution was not run; an additional vector initialization sequence
has a retained unresolved stall. The record distinguishes these limits from the
passing transfer tests.

[Timed vector addition](2026-10-06/ddr-vector-add.json) records the new bare-metal
DDR/SRAM buffer addition, scalar per-element comparison, positive/negative gates
and calibrated one-minute execution. `./scripts/ara ddr-add-test` runs the sanity
gates; `./scripts/ara ddr-add --target-seconds 3600` sizes an approximately one-hour
run for the local simulator. The hour-long execution itself is not part of the
recorded validation. Progress, PASS/FAIL and simulator-only `time -p` output are
visible without waveforms.

---

**[Cerebral Chips](https://www.cerebralchips.com) · Proton NPU**

Every machine should think.

## Programmable DMA — 7 October 2026

[DMA qualification](2026-10-07/dma.json) records 80 unit checks, 21 copy/transpose
transfers in each timing configuration, six rejected descriptors, negative gates
and all existing scalar/vector/matrix/DDR regressions. Source hashes identify the
executed RTL, test, integration patch and waveform checker.

[DMA waveform checks](2026-10-07/dma-waveform.json) and
[decoded transactions](2026-10-07/dma-transactions.csv) independently verify 257
reads and 257 writes, including high DDR addresses, byte masks and completion
ordering. Raw FST/VCD files stay in ignored artifacts. Reproduce with
`./scripts/ara dma-test`; see the [design and programming guide](../docs/dma.md).
