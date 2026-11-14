#!/usr/bin/env bash
# Install-test NexusOS .deb packages inside a disposable Ubuntu 26.04 container.
#
#   scripts/validation/test-packages-container.sh [DEB_DIR] [--image ubuntu:26.04]
#
# Verifies, without touching the host:
#   * nexusos-branding, nexusos-defaults and nexus-cli install with APT
#   * os-release diversion: NexusOS identity active, Ubuntu original preserved
#   * reinstall/upgrade keeps the diversion; removal restores Ubuntu's os-release
#   * the banner stays silent in non-interactive shells
#   * `nexus` commands run on the target Python/library versions
#   * nexusos-theme and nexusos-desktop dependencies resolve in resolute (simulation)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEB_DIR="$REPO_ROOT/build/debs"
IMAGE="ubuntu:26.04"
while [ $# -gt 0 ]; do
    case "$1" in
        --image) IMAGE="$2"; shift 2 ;;
        -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
        *) DEB_DIR="$(realpath "$1")"; shift ;;
    esac
done
ls "$DEB_DIR"/nexusos-branding_*.deb >/dev/null 2>&1 || { echo "no packages in $DEB_DIR" >&2; exit 1; }

proxy_args=()
for var in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY; do
    [ -n "${!var:-}" ] && proxy_args+=(-e "$var")
done
ca_args=()
if [ -n "${NEXUSOS_EXTRA_CA:-}" ] && [ -f "$NEXUSOS_EXTRA_CA" ]; then
    ca_args=(-v "$NEXUSOS_EXTRA_CA:/usr/local/share/ca-certificates/nexusos-extra.crt:ro")
fi

docker run --rm "${proxy_args[@]}" "${ca_args[@]}" -v "$DEB_DIR:/debs:ro" "$IMAGE" bash -euo pipefail -c '
    export DEBIAN_FRONTEND=noninteractive
    pass() { printf "PASS  %s\n" "$*"; }
    fail() { printf "FAIL  %s\n" "$*"; exit 1; }
    command -v update-ca-certificates >/dev/null && update-ca-certificates >/dev/null 2>&1 || true
    apt-get update -qq

    apt-get install -y -qq /debs/nexusos-branding_*.deb /debs/nexusos-defaults_*.deb /debs/python3-nexus-core_*.deb /debs/nexus-cli_*.deb >/dev/null
    pass "branding, defaults and nexus-cli installed"

    . /etc/os-release
    [ "$ID" = nexusos ] && [ "$ID_LIKE" = "ubuntu debian" ] && [ "$VERSION_ID" = 1.0 ] || fail "os-release identity ($ID/$ID_LIKE/$VERSION_ID)"
    [ "$PRETTY_NAME" = "NexusOS Engineering Edition 1.0" ] || fail "PRETTY_NAME=$PRETTY_NAME"
    [ "$UBUNTU_CODENAME" = resolute ] || fail "UBUNTU_CODENAME"
    pass "os-release: $PRETTY_NAME (ID=$ID, ID_LIKE=$ID_LIKE)"
    grep -q "^ID=ubuntu" /usr/lib/os-release.ubuntu || fail "Ubuntu os-release not preserved"
    divert=$(dpkg-divert --list /usr/lib/os-release)
    grep -q nexusos-branding <<<"$divert" || fail "diversion missing"
    pass "Ubuntu os-release preserved at /usr/lib/os-release.ubuntu (dpkg-divert)"
    grep -q "^NexusOS Engineering Edition" /etc/issue && grep -q "^Ubuntu" /etc/issue.ubuntu || fail "console banner /etc/issue"
    pass "console login banner: $(head -c 40 /etc/issue) (Ubuntu original kept as /etc/issue.ubuntu)"
    grep -q "^DISTRIB_ID=Ubuntu" /etc/lsb-release && pass "/etc/lsb-release untouched (Ubuntu)"
    [ "$(cat /etc/hostname 2>/dev/null || hostname)" != nexusos ] && pass "hostname not changed by package"

    out=$(sh -c ". /etc/profile.d/nexusos-banner.sh" 2>&1)
    [ -z "$out" ] || fail "banner printed in a non-interactive shell"
    pass "banner silent in non-interactive shells"
    [ -f /etc/xdg/fastfetch/config.jsonc ] && [ -f /usr/share/nexusos/skel/.zshrc ] && pass "fastfetch config and zshrc template installed"
    [ -f /usr/share/wallpapers/NexusOS/contents/images/3840x2160.png ] && pass "wallpaper packages rendered"
    [ -f /usr/share/icons/hicolor/scalable/apps/nexusos.svg ] && pass "nexusos icon installed"

    # Capture first: "cmd | grep -q" races under pipefail (grep exits at the first match).
    ver=$(nexus version) || fail "nexus version exit status"
    grep -q "NexusOS Engineering Edition 1.0" <<<"$ver" || fail "nexus version: $ver"
    grep -q "Crafted by Sanjay" <<<"$ver" || fail "nexus version credit"
    pass "nexus version -> $(head -1 <<<"$ver")"
    nexus system info --json | python3 -c "import json,sys; d=json.load(sys.stdin); assert d[\"os\"][\"id\"]==\"nexusos\"" || fail "system info json"
    pass "nexus system info reports NexusOS"
    set +e; nexus system health >/dev/null; rc=$?; set -e
    [ "$rc" -le 1 ] || fail "nexus system health exit $rc"
    pass "nexus system health ran (exit $rc)"
    set +e; nexus ai status >/dev/null; rc=$?; set -e
    [ "$rc" -eq 3 ] || fail "nexus ai status should exit 3 without Ollama (got $rc)"
    pass "nexus ai status handles missing Ollama (exit 3)"
    set +e; nexus infra containers >/dev/null 2>&1; rc=$?; set -e
    [ "$rc" -eq 3 ] || fail "nexus infra containers should exit 3 without Docker (got $rc)"
    pass "nexus infra containers handles missing Docker (exit 3)"
    cd /tmp && nexus dev create fastapi demo-api >/dev/null && [ -f demo-api/app/main.py ] || fail "fastapi scaffold"
    python3 -c "import ast,sys; ast.parse(open(\"demo-api/app/main.py\").read())"
    pass "nexus dev create fastapi generated a project"

    apt-get install -y -qq --simulate /debs/*.deb >/tmp/sim.log 2>&1 \
        || { tail -20 /tmp/sim.log; fail "theme/desktop dependency resolution"; }
    pass "nexusos-theme + nexusos-desktop dependencies resolve ($(grep -c "^Inst " /tmp/sim.log) packages would be installed)"

    dpkg -i /debs/nexusos-branding_*.deb >/dev/null
    divert=$(dpkg-divert --list /usr/lib/os-release)
    grep -q nexusos-branding <<<"$divert" && grep -q "^ID=nexusos" /usr/lib/os-release || fail "reinstall"
    pass "reinstall/upgrade keeps diversion"

    apt-get remove -y -qq nexus-cli python3-nexus-core nexusos-defaults nexusos-branding >/dev/null
    . /etc/os-release
    [ "$ID" = ubuntu ] || fail "os-release not restored after removal (ID=$ID)"
    [ ! -e /usr/lib/os-release.ubuntu ] || fail "stale os-release.ubuntu"
    grep -q "^Ubuntu" /etc/issue && [ ! -e /etc/issue.ubuntu ] || fail "/etc/issue not restored after removal"
    [ -z "$(dpkg-divert --list /usr/lib/os-release; dpkg-divert --list /etc/issue; dpkg-divert --list /etc/issue.net)" ] || fail "diversion left behind"
    pass "removal restores Ubuntu os-release ($PRETTY_NAME)"
    apt-get purge -y -qq nexusos-branding >/dev/null 2>&1 || true
    [ ! -e /etc/profile.d/nexusos-banner.sh ] || fail "conffile left after purge"
    grep -q "^Ubuntu" /etc/issue && grep -q "^Ubuntu" /etc/issue.net || fail "Ubuntu console banners missing after purge"
    pass "purge removes conffiles"
    echo "ALL PACKAGE TESTS PASSED"
'
