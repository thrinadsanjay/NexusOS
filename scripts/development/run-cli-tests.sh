#!/usr/bin/env bash
# Run the Nexus CLI unit tests (optionally with coverage if pytest-cov is installed).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
args=(tests/cli -q)
python3 -c "import pytest_cov" 2>/dev/null && args+=(--cov=nexus_cli --cov-report=term-missing)
PYTHONPATH="$REPO_ROOT/packages/nexus-cli${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m pytest "${args[@]}" "$@"
