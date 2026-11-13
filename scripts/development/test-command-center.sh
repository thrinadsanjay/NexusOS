#!/usr/bin/env bash
# Run the Command Center test suite: backend, agent, gateway, SSH, Docker/apps, modules and a
# headless UI smoke test (QT_QPA_PLATFORM=offscreen). Optional: --benchmark for resource numbers.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
python3 -m pytest command-center/tests -q "$@"
if [ "${1:-}" = "--benchmark" ]; then
    scripts/benchmarks/command-center.sh --idle 10 --runs 3
fi
