#!/usr/bin/env bash
# Run the nexus CLI tests (v0.1 and v0.2 command groups) against the shared nexus_core backend.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
exec python3 -m pytest tests/cli -q "$@"
