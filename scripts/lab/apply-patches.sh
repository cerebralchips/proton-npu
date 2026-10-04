#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
for patch in "$LAB_ROOT"/patches/ara/*.patch; do
  if git -C "$ARA_DIR" apply --reverse --check "$patch" 2>/dev/null; then
    echo "Already applied: $(basename "$patch")"
  else
    git -C "$ARA_DIR" apply --check "$patch"
    git -C "$ARA_DIR" apply "$patch"
    echo "Applied: $(basename "$patch")"
  fi
done
for patch in "$LAB_ROOT"/patches/cva6/*.patch; do
  [[ -f "$patch" ]] || continue
  if git -C "$ARA_DIR/hardware/deps/cva6" apply --reverse --check "$patch" 2>/dev/null; then
    echo "Already applied: cva6/$(basename "$patch")"
  else
    git -C "$ARA_DIR/hardware/deps/cva6" apply --check "$patch"
    git -C "$ARA_DIR/hardware/deps/cva6" apply "$patch"
  fi
done
