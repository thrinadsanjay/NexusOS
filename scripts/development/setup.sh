#!/usr/bin/env bash
# Set up a NexusOS development environment in a Python virtual environment.
#
#   scripts/development/setup.sh [VENV_DIR]     (default: .venv)
#
# Installs nexus-core, the management agent, the Command Center (PySide6) and nexus-cli in
# editable mode, plus ruff, yamllint and pytest, into the venv only. System packages needed for packaging and branding checks are
# printed, never installed automatically (no sudo is run).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="${1:-$REPO_ROOT/.venv}"

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
# Third-party dependencies from PyPI; NexusOS projects in editable mode without dependency resolution
# (they depend on each other by name, which is not published on PyPI).
"$VENV/bin/python" -m pip install --quiet "pydantic>=2.5" "httpx>=0.27" PyYAML "typer>=0.12" "rich>=13.7" \
    paramiko secretstorage "PySide6-Essentials>=6.5" fastapi pytest ruff==0.16.9 yamllint
for project in command-center/backend command-center/privileged-agent command-center/frontend packages/nexus-cli; do
    "$VENV/bin/python" -m pip install --quiet --no-deps -e "$REPO_ROOT/$project"
done
echo "venv ready: . $VENV/bin/activate"

missing=()
for tool in dpkg-buildpackage dh lintian rsvg-convert optipng shellcheck xorriso desktop-file-validate docker openssl ssh-keygen; do
    command -v "$tool" >/dev/null || missing+=("$tool")
done
if [ ${#missing[@]} -gt 0 ]; then
    echo
    echo "Optional system tools not found: ${missing[*]}"
    echo "Install them yourself if you need packaging/branding/ISO checks:"
    echo "  sudo apt install dpkg-dev debhelper dh-python pybuild-plugin-pyproject python3-all \\"
    echo "       lintian librsvg2-bin optipng plymouth-theme-spinner fonts-inter fonts-jetbrains-mono shellcheck xorriso desktop-file-utils \\"
    echo "       openssl openssh-client libegl1 libgl1 docker.io"
fi
