#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
mkdir -p "$LAB_TOOLS/downloads" "$LAB_TOOLS/bin" "$LAB_TOOLS/src" "$LAB_TOOLS/build" "$LAB_ROOT/artifacts"
exec > >(tee -a "$LAB_ROOT/artifacts/provision.log") 2>&1
date -u
[[ $(uname -m) == aarch64 ]] || { echo 'This provisioning profile requires Linux ARM64.'; exit 1; }
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential autoconf automake bison flex \
  libfl-dev libelf-dev libboost-regex-dev libboost-system-dev device-tree-compiler libgmp-dev \
  libmpfr-dev libmpc-dev libisl-dev zlib1g-dev libzstd-dev libxml2-dev libtinfo6 cmake ninja-build \
  git curl xz-utils python3 python3-yaml python3-numpy help2man texinfo gtkwave
python3 - "$LAB_ROOT" <<'PY'
import json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]); pin=json.loads((root/'sources.lock.json').read_text())['ara']
src=root/'upstream/ara'
if not (src/'.git').exists():
    src.parent.mkdir(exist_ok=True)
    subprocess.run(['git','clone','--no-checkout','--depth','1',pin['url'],str(src)],check=True)
    subprocess.run(['git','fetch','--depth','1','origin',pin['commit']],cwd=src,check=True)
    subprocess.run(['git','checkout','--detach',pin['commit']],cwd=src,check=True)
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=src,text=True).strip()
if head!=pin['commit']: raise SystemExit('Ara revision differs from the lock. Preserve changes and resolve explicitly.')
PY
python3 - "$LAB_ROOT/sources.lock.json" "$LAB_TOOLS/downloads" <<'PY'
import hashlib,json,pathlib,subprocess,sys
lock=json.load(open(sys.argv[1])); dest=pathlib.Path(sys.argv[2])
for name in ['llvm','bender']:
    item=lock[name]; path=dest/item['url'].rsplit('/',1)[1]
    if not path.exists():
        partial=path.with_suffix(path.suffix+'.partial')
        subprocess.run(['curl','-fL','--retry','3','-C','-','-o',str(partial),item['url']],check=True)
        partial.rename(path)
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    if h.hexdigest()!=item['sha256']: raise SystemExit(f'Checksum mismatch: {path}')
    print(f'{name}: SHA-256 verified',flush=True)
PY
if [[ ! -x "$LAB_TOOLS/llvm/bin/clang" ]]; then
  mkdir -p "$LAB_TOOLS/llvm"
  tar -xJf "$LAB_TOOLS/downloads/LLVM-20.1.0-Linux-ARM64.tar.xz" --strip-components=1 -C "$LAB_TOOLS/llvm"
fi
if [[ ! -x "$LAB_TOOLS/bin/bender" ]]; then
  tar -xzf "$LAB_TOOLS/downloads/bender-0.31.0-arm64-linux-gnu-ubuntu24.04.tar.gz" -C "$LAB_TOOLS/bin"
fi
"$LAB_TOOLS/llvm/bin/clang" --version
"$LAB_TOOLS/bin/bender" --version
bash "$LAB_ROOT/scripts/lab/prepare-deps.sh"
bash "$LAB_ROOT/scripts/lab/apply-patches.sh"
bash "$LAB_ROOT/scripts/lab/toolchain.sh"
if [[ ! -x "$VERIL_INSTALL_DIR/bin/verilator" ]]; then
  cd "$ARA_DIR/toolchain/verilator"
  autoconf
  cd "$LAB_TOOLS/build"
  mkdir -p verilator
  cd verilator
  "$ARA_DIR/toolchain/verilator/configure" --prefix="$VERIL_INSTALL_DIR" CC="$LAB_TOOLS/llvm/bin/clang" CXX="$LAB_TOOLS/llvm/bin/clang++"
  make -j"$NUM_JOBS"
  make install
fi
echo 'Hardware dependencies, LLVM, Verilator and Spike provisioned.'
