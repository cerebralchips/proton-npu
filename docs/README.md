# Proton NPU documentation

[Open the architecture website](https://cerebralchips.github.io/proton-npu/).
For offline use, download/clone the repository and open `docs/index.html`.
The HTML pages use only local CSS and SVG assets.

![System architecture: CPU, vector and matrix units, programmable DMA, SRAM and DDR](assets/system.svg)

The system view shows the optional DMA configuration. The CPU programs DMA
registers through AXI; a separate DMA master copies or transposes data between
SRAM and DDR. Matrix tile buffers remain CPU-fed.

| Guide | Contents |
| --- | --- |
| [Proton NPU](index.html) | Complete system, data flow and measured baseline |
| [64-bit RISC-V core](cva6.html) | Scalar CPU, conceptual pipeline, retirement and command ordering |
| [RVV 1.0 vector unit](ara.html) | RVV execution, two-lane organization and memory path |
| [INT8 matrix engine](matrix.html) | Packed INT8 PEs, buffers, command contract and result handling |
| [Programmable DMA](dma.md) | SRAM/DDR copy and transpose, register ABI, cache ownership and waveform verification |
| [Contributor guide](contributing.html) | Source map and verification workflow |
| [PE explorer](pe-array-explorer.html) | Interactive arithmetic teaching model |

Technical notes: [setup](environment.md), [first lesson](lesson.md),
[waveforms](waveforms.md), [matrix design contract](matrix-design.md),
[matrix commands](matrix-running.md), [status](status.md),
[SRAM + DDR simulation and timed examples](ddr-simulation.md),
and [portable verification records](../verification/README.md).

The optional DDR target exposes 16 MiB internal SRAM and 4 GiB external functional
memory to both CPU and vector loads/stores. Physical FPGA/ASIC DDR requires a
controller and PHY. Model deployment and compiler/runtime placement live in
[proton-sdk](https://github.com/cerebralchips/proton-sdk); its target manifest pins
the hardware revision used for numerical verification. SDK DMA scheduling is not
yet integrated. The DMA is not cache coherent; its qualified bare-metal test
disables the data cache and uses fences around transfers.

---

**[Cerebral Chips](https://www.cerebralchips.com) · Proton NPU**

Every machine should think.
