#!/usr/bin/env bash
# Use Ara's LLVM version with RV64 LP64D Newlib/libgcc.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
bash "$LAB_ROOT/scripts/lab/build-runtime.sh"
GCC_ROOT="$ARA_GCC_ROOT"
mkdir -p "$LLVM_INSTALL_DIR/bin"
python3 - "$LLVM_INSTALL_DIR/bin" "$LAB_TOOLS/llvm" "$GCC_ROOT" <<'PY'
import pathlib,shlex,subprocess,sys
dest,llvm,gcc=map(pathlib.Path,sys.argv[1:])
cc=[str(gcc/'bin/riscv-none-elf-gcc'),'-march=rv64gc','-mabi=lp64d']
libgcc=pathlib.Path(subprocess.check_output([*cc,'-print-libgcc-file-name'],text=True).strip()).parent
libc=pathlib.Path(subprocess.check_output([*cc,'-print-file-name=libc.a'],text=True).strip()).resolve().parent
for tool in ['llvm-objdump','llvm-objcopy','llvm-as','llvm-ar','llvm-nm','llvm-ranlib','llvm-strip','ld.lld']:
    p=dest/tool
    if p.is_symlink(): p.unlink()
    p.symlink_to(llvm/'bin'/tool)
for tool in ['clang','clang++']:
    args=[str(llvm/'bin'/tool),'--target=riscv64-unknown-elf',
          '--sysroot='+str(gcc/'riscv-none-elf'),
          '-L'+str(libgcc), '-L'+str(libc),
          '--rtlib=libgcc', '--unwindlib=none']
    p=dest/tool
    p.write_text('#!/usr/bin/env bash\nexec '+shlex.join(args)+' "$@"\n')
    p.chmod(0o755)
PY
"$LLVM_INSTALL_DIR/bin/clang" --version
