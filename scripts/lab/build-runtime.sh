#!/usr/bin/env bash
# Resumable builds using the exact upstream toolchain versions/configure flags.
set -eo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
export ROOT_DIR="$ARA_DIR/hardware/deps/cva6/util/toolchain-builder"
export SRC_DIR="$LAB_TOOLS/src/gcc-13.1.0"
export BUILD_DIR="$LAB_TOOLS/build/gcc-13.1.0"
export INSTALL_DIR="$ARA_GCC_ROOT"
mkdir -p "$SRC_DIR" "$BUILD_DIR"
exec 8>"$BUILD_DIR/lab.lock"
flock -n 8 || { echo 'Another toolchain build is running.' >&2; exit 1; }
check_compiler() {
  "$ARA_GCC_ROOT/bin/riscv-none-elf-gcc" -dumpfullversion -dumpversion
  for library in libc.a libm.a libgcc.a; do
    library_path=$("$ARA_GCC_ROOT/bin/riscv-none-elf-gcc" -march=rv64gc -mabi=lp64d "-print-file-name=$library")
    [[ -f "$library_path" ]] || { echo "Missing RV64 LP64D $library" >&2; return 1; }
  done
  "$ARA_GCC_ROOT/bin/riscv-none-elf-gcc" -march=rv64gc -mabi=lp64d -x c -S -o "$BUILD_DIR/tls-check.s" - <<'C'
#include <stdio.h>
#include <sys/signal.h>
__thread int proton_tls_probe;
int read_tls_probe(void) { return proton_tls_probe; }
C
  if grep -q __emutls "$BUILD_DIR/tls-check.s"; then
    echo 'This toolchain uses emulated TLS; CVA6 support code requires native TLS.' >&2
    return 1
  fi
}
if [[ -f "$INSTALL_DIR/.proton-toolchain-complete" ]] || \
   [[ "$ARA_GCC_ROOT" != "$LAB_TOOLS/gcc-13.1.0" && -x "$ARA_GCC_ROOT/bin/riscv-none-elf-gcc" ]]; then
  check_compiler
  exit 0
fi
# Do not populate or repair an arbitrary caller-supplied toolchain directory.
if [[ "$ARA_GCC_ROOT" != "$LAB_TOOLS/gcc-13.1.0" ]]; then
  echo "ARA_GCC_ROOT must point to a complete GCC/Newlib installation." >&2
  exit 1
fi
if [[ ! -x "$SRC_DIR/gcc/configure" || ! -x "$SRC_DIR/binutils-gdb/configure" || ! -x "$SRC_DIR/newlib/configure" ]]; then
  bash -e "$ROOT_DIR/get-toolchain.sh" gcc-13.1.0-baremetal
fi
mkdir -p "$INSTALL_DIR"
source "$ROOT_DIR/config/global.sh"
source "$ROOT_DIR/config/gcc-13.1.0-baremetal.sh"
export PATH="$INSTALL_DIR/bin:$PATH"

mkdir -p "$BUILD_DIR/binutils-riscv-none-elf/gas/doc"
cd "$BUILD_DIR/binutils-riscv-none-elf"
[[ -f Makefile ]] || CFLAGS=-O2 CXXFLAGS=-O2 \
  "$SRC_DIR/$BINUTILS_DIR/configure" $(BINUTILS_CONFIGURE_OPTS riscv-none-elf)
make -j"$NUM_JOBS"
make install

mkdir -p "$BUILD_DIR/gcc"
cd "$BUILD_DIR/gcc"
[[ -f Makefile ]] || CFLAGS=-O2 CXXFLAGS=-O2 \
  "$SRC_DIR/$GCC_DIR/configure" $(GCC_CONFIGURE_OPTS)
make -j"$NUM_JOBS"
make install

mkdir -p "$BUILD_DIR/newlib-riscv-none-elf"
cd "$BUILD_DIR/newlib-riscv-none-elf"
[[ -f Makefile ]] || \
  CFLAGS_FOR_TARGET='-O2 -mcmodel=medany -Wno-unused-command-line-argument -Wno-implicit-function-declaration -Wno-int-conversion' \
  "$SRC_DIR/$NEWLIB_DIR/configure" $(NEWLIB_CONFIGURE_OPTS riscv-none-elf)
make -j"$NUM_JOBS"
make install
check_compiler
touch "$INSTALL_DIR/.proton-toolchain-complete"
