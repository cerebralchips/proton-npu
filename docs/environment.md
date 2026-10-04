# Environment and reproducibility

The validated simulation environment is Ubuntu 24.04 ARM64 on Apple Silicon,
with 6 virtual CPUs, 8 GiB RAM, 4 GiB swap and a 60 GiB sparse VM disk.
A 16 GiB Mac was used with four compile jobs. Hardware simulation runs in Linux;
RISC-V applications execute in the Verilated CPU model.

## Fresh checkout

```bash
git clone --branch hardware https://github.com/cerebralchips/proton-npu.git
cd proton-npu
./scripts/ara vm-start
./scripts/ara provision
./scripts/ara doctor
./scripts/ara matrix
```

On ARM64 Ubuntu, skip the VM command. Intel/x86 provisioning is not implemented
by this profile. On macOS, `vm-start` checksums and installs Lima 2.2.0 under ignored
`.tools/` if necessary, and creates `proton-npu` with the pinned Ubuntu image in
[the VM template](../infra/lima/proton-npu.yaml). The checkout is mounted writable
at `/ara-workspace`; this avoids spaces in guest build paths. VM state defaults to
`~/.local/share/proton-npu/lima`. Existing earlier `cva6` lab installations are
recognized and reused for compatibility.

Optional overrides: `ARA_LIMACTL`, `ARA_LIMA_HOME`, `ARA_VM`, `NUM_JOBS` (default 4),
`ARA_LAB_TOOLS`, and `ARA_GCC_ROOT`. The last two are **guest Linux paths** on macOS.
If using an existing custom VM, its `/ara-workspace` mount must point to this
checkout. Do not run multiple large VMs on a memory-constrained host.

## Sources and tools

Exact revisions/checksums are in [sources.lock.json](../sources.lock.json).
Provisioning clones Ara, obtains its Bender-locked dependencies, applies patches,
installs LLVM and builds the pinned simulation tools. An unexpected Ara revision
is rejected. Downloads/builds stay in ignored `upstream/`, `artifacts/` and guest
`~/.local/share/ara-lab`. Ubuntu package repositories are not a hermetic snapshot.

| Component | Selection |
| --- | --- |
| Ara | `34bd3bc152421b4601a7bf3d6e8e91ffb545c99e` |
| Matched PULP CVA6 | `99eac9a649001bdf5b8f9da52e0ca73d5c48db1c` |
| Hardware | `2_lanes`, VLEN 2048, real CVA6 enabled |
| LLVM | 20.1.0 official Linux ARM64 binary |
| Bender | 0.31.0 Ubuntu 24.04 ARM64 binary |
| Verilator | Ara-pinned `06263ec724e7bf1fb0a0366b3aec54cd431c51d6` |
| Spike | Ara-pinned `204b88deda9bcb7537bc09ae5c320f691e8839ef` |
| C runtime | GCC 13.1.0 / Newlib 4.3.0, RV64 LP64D multilib |

LLVM compiles applications. The runtime adapter uses Newlib/libgcc rather than
Ara's source-built Newlib/compiler-rt recipe. `ARA_GCC_ROOT` can provide an existing
complete runtime; the original scalar-lab runtime is reused read-only if present.
Otherwise `build-runtime.sh` builds a private copy using the matched CVA6 recipe.
The wrapper explicitly selects the RV64 LP64D libraries, not GCC's default ABI.
The native ARM64 `clang++` compiles simulator C++; the RISC-V wrapper is only for
application builds. C++ exception support is outside this C application profile.

The recorded RTL runs use the existing validated runtime. The new automatic VM
creation and cold GCC source-build path have been syntax/configuration checked,
but have not yet been exercised together on a second clean machine. Reuse of the
existing environment is checked by the publication validation. Allow extra time
and disk for the cold runtime build; do not mistake this for a container image
with every host package pinned.

## Patches and isolation

Five [Ara patches](../patches/ara) repair waiver characters, Spike linker
subsections, decimal cycle reporting, testbench build dependencies, and add the
matrix system integration. The [CVA6 patch](../patches/cva6) adds matrix instruction
ordering and valid/ready accelerator accounting under `MATRIX_ENABLE`.
Ara's required `tech_cells_generic` SRAM simulation patch is also applied.
Matrix-disabled and matrix-enabled builds remain separate and selectable.

Builds, provisioning and simulation share a guest file lock. Waveform and
non-waveform simulators have separate directories. All runs preserve logs and
metadata under `artifacts/`; no large FSTs or binaries belong in the source commit.

For larger programs, check the loader's 1 MiB ELF load window, actual simulated
RAM, linker layout and stack/heap requirements. A linker declaration alone does
not establish available memory. Linux, IREE and physical implementation need
separate milestones; see [current status](status.md).

---

**[Cerebral Chips](https://www.cerebralchips.com) · Proton NPU**

Every machine should think.
