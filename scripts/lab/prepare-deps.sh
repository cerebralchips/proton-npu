#!/usr/bin/env bash
# Can run while the larger LLVM release is downloading.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
mkdir -p "$LAB_TOOLS/downloads" "$LAB_TOOLS/bin" "$LAB_TOOLS/build/spike"
exec > >(tee -a "$LAB_ROOT/artifacts/dependencies.log") 2>&1
archive="$LAB_TOOLS/downloads/bender-0.31.0-arm64-linux-gnu-ubuntu24.04.tar.gz"
if [[ ! -f "$archive" ]]; then
  curl -fsSL --retry 3 -o "$archive.tmp" https://github.com/pulp-platform/bender/releases/download/v0.31.0/bender-0.31.0-arm64-linux-gnu-ubuntu24.04.tar.gz
  echo "117af7701628db067fb3b4c34b5ab0bcead77102ef378aacbb8e8bf4887131bf  $archive.tmp" | sha256sum -c -
  mv "$archive.tmp" "$archive"
fi
tar -xzf "$archive" -C "$LAB_TOOLS/bin"
cd "$ARA_DIR"
git submodule update --init --depth 1 -- toolchain/riscv-isa-sim toolchain/verilator
ln -sfn "$LAB_TOOLS/bin/bender" hardware/bender
make -C hardware checkout
if ! git -C hardware/deps/tech_cells_generic apply --reverse --check ../../patches/0001-tech-cells-generic-sram.patch 2>/dev/null; then
  git -C hardware/deps/tech_cells_generic apply --check ../../patches/0001-tech-cells-generic-sram.patch
  make -C hardware apply-patches
fi
if [[ ! -x "$ISA_SIM_INSTALL_DIR/bin/spike" ]]; then
  cd "$LAB_TOOLS/build/spike"
  "$ARA_DIR/toolchain/riscv-isa-sim/configure" --prefix="$ISA_SIM_INSTALL_DIR" --without-boost --without-boost-asio --without-boost-regex
  make -j"$NUM_JOBS"
  make install
fi
