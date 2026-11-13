#!/usr/bin/env bash
# Full local validation: lint, YAML, manifests (+ archive check with --archive), branding,
# Debian metadata, application registry, shellcheck, QML lint, all tests.
#   scripts/development/validate.sh [--archive] [--debs DIR]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
args=()
ARCHIVE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --archive) ARCHIVE=1; shift ;;
        --debs) args+=(--debs "$2"); shift 2 ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done
[ "$ARCHIVE" -eq 1 ] && python3 scripts/validation/validate_manifests.py --check-archive
exec scripts/validation/run-all.sh "${args[@]}"
