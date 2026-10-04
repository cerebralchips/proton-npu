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

---

**[Cerebral Chips](https://www.cerebralchips.com) · Proton NPU**

Every machine should think.
