#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
python3 "$LAB_ROOT/scripts/lab/apply-stack.py" "$ARA_DIR" "$LAB_ROOT/patches/ara"
for patch in "$LAB_ROOT"/patches/cva6/*.patch; do
  [[ -f "$patch" ]] || continue
  if git -C "$ARA_DIR/hardware/deps/cva6" apply --reverse --check "$patch" 2>/dev/null; then
    echo "Already applied: cva6/$(basename "$patch")"
  else
    git -C "$ARA_DIR/hardware/deps/cva6" apply --check "$patch"
    git -C "$ARA_DIR/hardware/deps/cva6" apply "$patch"
  fi
done
