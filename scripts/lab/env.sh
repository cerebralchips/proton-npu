#!/usr/bin/env bash
LAB_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
export ARA_DIR="$LAB_ROOT/upstream/ara"
export LAB_TOOLS=${ARA_LAB_TOOLS:-"$HOME/.local/share/ara-lab"}
export NUM_JOBS=${NUM_JOBS:-4}
export ARA_CONFIGURATION=2_lanes
export LLVM_INSTALL_DIR="$LAB_TOOLS/riscv-llvm"
export ISA_SIM_INSTALL_DIR="$LAB_TOOLS/spike"
export VERIL_INSTALL_DIR="$LAB_TOOLS/verilator"
# Host C++ compilation must resolve native clang++, not the RISC-V wrapper.
export PATH="$LAB_TOOLS/llvm/bin:$LLVM_INSTALL_DIR/bin:$VERIL_INSTALL_DIR/bin:$LAB_TOOLS/bin:$PATH"

# LLVM uses the RV64 LP64D Newlib/libgcc runtime. An explicit override wins.
if [[ -z "${ARA_GCC_ROOT:-}" ]]; then
  if [[ -x "$HOME/.local/share/cva6-lab/gcc-13.1.0/bin/riscv-none-elf-gcc" ]]; then
    export ARA_GCC_ROOT="$HOME/.local/share/cva6-lab/gcc-13.1.0"
  else
    export ARA_GCC_ROOT="$LAB_TOOLS/gcc-13.1.0"
  fi
fi
