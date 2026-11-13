#!/usr/bin/env bash
# Build all NexusOS .deb packages in a disposable ubuntu:26.04 container (reference build),
# validate their contents and write checksums. Falls back to a host build with --host.
#
#   scripts/development/build-packages.sh [--host] [--out DIR] [PACKAGE ...]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$REPO_ROOT/build/debs"
HOST=0
args=()
while [ $# -gt 0 ]; do
    case "$1" in
        --host) HOST=1; shift ;;
        --out) OUT="$(realpath -m "$2")"; shift 2 ;;
        *) args+=("$1"); shift ;;
    esac
done
if [ "$HOST" -eq 1 ]; then
    "$REPO_ROOT/scripts/package/build-deb.sh" --out "$OUT" "${args[@]}"
else
    "$REPO_ROOT/scripts/package/build-in-container.sh" --out "$OUT" "${args[@]}"
fi
python3 "$REPO_ROOT/scripts/validation/validate_debian.py" --debs "$OUT"
"$REPO_ROOT/scripts/build/checksums.sh" generate "$OUT"
