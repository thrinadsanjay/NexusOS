#!/usr/bin/env bash
# Run every NexusOS check that is available on this machine and summarise the results.
#
#   scripts/validation/run-all.sh [--debs DIR]
#
# Checks that need missing tools are reported as SKIPPED (with the reason), not failed.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1
DEBS=""
[ "${1:-}" = "--debs" ] && DEBS="${2:-}"

declare -a results=()
failed=0
run() { # name command...
    local name="$1"; shift
    printf '\n\033[38;2;49;198;189m== %s ==\033[0m\n' "$name"
    if "$@"; then results+=("PASS     $name"); else results+=("FAIL     $name"); failed=1; fi
}
skip() { printf '\n== %s ==\nskipped: %s\n' "$1" "$2"; results+=("SKIPPED  $1 ($2)"); }
have() { command -v "$1" >/dev/null 2>&1; }

export PYTHONPATH="$REPO_ROOT/command-center/backend:$REPO_ROOT/command-center/privileged-agent:$REPO_ROOT/command-center/frontend:$REPO_ROOT/packages/nexus-cli${PYTHONPATH:+:$PYTHONPATH}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"

if have ruff; then run "ruff lint" ruff check .; run "ruff format check" ruff format --check packages/nexus-cli command-center scripts tests
else skip "ruff" "ruff not installed"; fi
if have yamllint; then run "yamllint" yamllint -s .; else skip "yamllint" "yamllint not installed"; fi
run "manifests" python3 scripts/validation/validate_manifests.py
run "branding" python3 scripts/validation/validate_branding.py
run "application registry" python3 scripts/validation/validate_apps.py
run "secret scan" python3 scripts/validation/check_secrets.py
if [ -n "$DEBS" ]; then run "debian metadata + .debs" python3 scripts/validation/validate_debian.py --debs "$DEBS"
else run "debian metadata" python3 scripts/validation/validate_debian.py; fi
if have shellcheck; then
    mapfile -t shells < <(find scripts iso configs packages -type f \( -name '*.sh' -o -name '*.preinst' -o -name '*.postrm' \) \
        -not -path '*/build/*' | sort)
    run "shellcheck" shellcheck "${shells[@]}"
else skip "shellcheck" "shellcheck not installed"; fi
if have desktop-file-validate; then run "desktop files" desktop-file-validate packages/nexusos-desktop/applications/*.desktop
else skip "desktop files" "desktop-file-validate not installed"; fi
# shellcheck disable=SC2317  # invoked indirectly through run()
qmllint_errors() {
    local out
    local -a qml_files
    mapfile -t qml_files < <(find command-center -name '*.qml')
    out="$(pyside6-qmllint -I command-center/frontend/qml "${qml_files[@]}" 2>&1 || true)"
    ! grep -q '^Error:' <<<"$out"
}
if have pyside6-qmllint; then run "QML lint (errors)" qmllint_errors
else skip "QML lint" "pyside6-qmllint not installed"; fi
if have node; then run "layout.js syntax" node --check desktop/panels/org.kde.plasma.desktop-layout.js
else skip "layout.js syntax" "node not installed"; fi
if [ -n "$DEBS" ]; then export NEXUSOS_DEB_DIR="$DEBS"; fi
run "pytest" python3 -m pytest -q

printf '\n==================== summary ====================\n'
printf '%s\n' "${results[@]}"
exit "$failed"
