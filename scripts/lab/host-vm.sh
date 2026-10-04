#!/usr/bin/env bash
# Bootstrap Lima on Apple Silicon without Homebrew or a sibling source checkout.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
LIMACTL=$1
VM=$2
[[ $(uname -s) == Darwin && $(uname -m) == arm64 ]] || {
  echo 'vm-start supports Apple Silicon. On ARM64 Ubuntu, run provision directly.' >&2
  exit 1
}
if [[ ! -x "$LIMACTL" ]]; then
  [[ "$LIMACTL" == "$ROOT/.tools/lima/bin/limactl" ]] || {
    echo "Missing configured Lima executable: $LIMACTL" >&2; exit 1;
  }
  python3 - "$ROOT" <<'PY'
import hashlib, json, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
pin = json.loads((root/'sources.lock.json').read_text())['lima']
dest = root/'.tools/lima'
dest.mkdir(parents=True, exist_ok=True)
archive = dest/'release.tar.gz'
subprocess.run(['curl', '-fL', '--retry', '3', '-o', str(archive), pin['url']], check=True)
if hashlib.sha256(archive.read_bytes()).hexdigest() != pin['sha256']:
    raise SystemExit('Lima checksum mismatch')
subprocess.run(['tar', '-xzf', str(archive), '-C', str(dest)], check=True)
archive.unlink()
PY
fi
if [[ ! -f "$LIMA_HOME/$VM/lima.yaml" ]]; then
  mkdir -p "$ROOT/.tools"
  python3 - "$ROOT" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
template = (root/'infra/lima/proton-npu.yaml').read_text()
(root/'.tools/proton-npu.yaml').write_text(template.replace('__REPO__', json.dumps(str(root))))
PY
  exec "$LIMACTL" start --tty=false --name="$VM" "$ROOT/.tools/proton-npu.yaml"
fi
exec "$LIMACTL" start --tty=false "$VM"
