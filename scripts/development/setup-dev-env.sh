#!/usr/bin/env bash
# Set up a NexusOS development environment in a Python virtual environment.
#
#   scripts/development/setup-dev-env.sh [VENV_DIR]     (default: .venv)
#
# Installs nexus-cli in editable mode with test extras, plus ruff, yamllint and pytest,
# into the venv only. System packages needed for packaging and branding checks are
# printed, never installed automatically (no sudo is run).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="${1:-$REPO_ROOT/.venv}"

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -e "$REPO_ROOT/packages/nexus-cli[test]" ruff yamllint pyyaml pytest
echo "venv ready: . $VENV/bin/activate"

missing=()
for tool in dpkg-buildpackage dh lintian rsvg-convert optipng shellcheck xorriso desktop-file-validate; do
    command -v "$tool" >/dev/null || missing+=("$tool")
done
if [ ${#missing[@]} -gt 0 ]; then
    echo
    echo "Optional system tools not found: ${missing[*]}"
    echo "Install them yourself if you need packaging/branding/ISO checks:"
    echo "  sudo apt install dpkg-dev debhelper dh-python pybuild-plugin-pyproject python3-all \\"
    echo "       lintian librsvg2-bin optipng fonts-inter fonts-jetbrains-mono shellcheck xorriso desktop-file-utils"
fi
