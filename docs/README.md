# Proton NPU documentation

[Open the architecture website](https://cerebralchips.github.io/proton-npu/).
For offline use, download/clone the repository and open `docs/index.html`.
The HTML pages use only local CSS and SVG assets.

![System architecture](assets/system.svg)

| Guide | Contents |
| --- | --- |
| [Proton NPU](index.html) | Complete system, data flow and measured baseline |
| [CVA6](cva6.html) | Scalar CPU, conceptual pipeline, retirement and command ordering |
| [Ara](ara.html) | RVV execution, two-lane organization and memory path |
| [Matrix](matrix.html) | Packed INT8 PEs, buffers, command contract and result handling |
| [Contributor guide](contributing.html) | Source map and verification workflow |
| [PE explorer](pe-array-explorer.html) | Interactive arithmetic teaching model |

Technical notes: [setup](environment.md), [first lesson](lesson.md),
[waveforms](waveforms.md), [matrix design contract](matrix-design.md),
[matrix commands](matrix-running.md), [status](status.md),
and [portable verification records](../verification/README.md).
