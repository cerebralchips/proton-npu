#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
mkdir -p "$LAB_ROOT/artifacts" "$LAB_TOOLS"
# Provisioning and execution share generated files and must not overlap.
exec 9>"$LAB_TOOLS/run.lock"
flock -n 9 || { echo 'Another Ara build/run is active. Wait for it to finish.' >&2; exit 1; }
case "${1:-help}" in
  provision)
    exec bash "$LAB_ROOT/scripts/lab/provision.sh"
    ;;
  build|hello|run|smoke|wave)
    exec python3 "$LAB_ROOT/scripts/lab/run.py" "$@"
    ;;
  matrix-unit|matrix|matrix-wave|matrix-smoke|matrix-negative)
    exec python3 "$LAB_ROOT/scripts/lab/matrix.py" "$@"
    ;;
  ddr-build|ddr-test|ddr-unit)
    exec python3 "$LAB_ROOT/scripts/lab/ddr.py" "$@"
    ;;
  ddr-sweep|ddr-sweep-smoke)
    exec python3 "$LAB_ROOT/scripts/lab/ddr-sweep.py" "$@"
    ;;
  ddr-add|ddr-add-test)
    exec python3 "$LAB_ROOT/scripts/lab/ddr-add.py" "$@"
    ;;
  doctor)
    exec python3 "$LAB_ROOT/scripts/lab/doctor.py"
    ;;
  *) echo 'Unknown guest command.' >&2; exit 2 ;;
esac
