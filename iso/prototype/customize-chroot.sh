#!/usr/bin/env bash
# NexusOS prototype customisation -- run INSIDE Cubic's chroot terminal (never on a real system).
#
#   1. In Cubic, copy the NexusOS .deb files and this repository's manifests/ into the
#      chroot (Cubic's terminal has a "Copy" button), e.g. to /root/nexusos/.
#   2. Run:  bash /root/nexusos/customize-chroot.sh /root/nexusos
#
# Expected layout of the directory argument:
#   debs/*.deb                 nexusos-branding, nexusos-theme, nexusos-defaults, nexusos-desktop, nexus-cli
#   manifests/*.yaml           copied from the repository
#
# What it does (all inside the chroot being turned into the ISO):
#   * installs the NexusOS packages with APT (dependencies come from the Ubuntu archive)
#   * installs the "development" and "infrastructure" manifest packages unless --minimal
#   * copies the NexusOS zsh template into /etc/skel for accounts created by the installer
#   * never installs Ollama/Open WebUI and never downloads AI models
#
# Safety: refuses to run outside a chroot (checked with ischroot(1)).
set -euo pipefail

SRC="${1:-}"
MINIMAL=0
[ "${2:-}" = "--minimal" ] && MINIMAL=1
die() { printf 'customize-chroot: %s\n' "$*" >&2; exit 1; }

if [ -z "$SRC" ] || [ ! -d "$SRC/debs" ] || [ ! -d "$SRC/manifests" ]; then
    die "usage: $0 DIR [--minimal]  (DIR needs debs/ and manifests/)"
fi
if ! ischroot; then
    die "this script modifies the system it runs on and must only run inside Cubic's chroot"
fi
[ "$(id -u)" -eq 0 ] || die "run as root inside the chroot"

export DEBIAN_FRONTEND=noninteractive

# Package names from a manifest group, read with python3-yaml (present on Kubuntu media).
manifest_packages() { # file group
    python3 - "$1" "$2" <<'PY'
import sys, yaml
data = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
print("\n".join((data.get("packages") or {}).get(sys.argv[2]) or []))
PY
}

echo "==> Refreshing package indexes"
apt-get update

echo "==> Installing base + desktop manifest packages"
mapfile -t pkgs < <(
    for m in base desktop; do
        manifest_packages "$SRC/manifests/$m.yaml" mandatory
        manifest_packages "$SRC/manifests/$m.yaml" recommended
    done | sort -u
)
apt-get install -y --no-install-recommends "${pkgs[@]}"

if [ "$MINIMAL" -eq 0 ]; then
    echo "==> Installing development + infrastructure manifest packages"
    mapfile -t extra < <(
        for m in development infrastructure; do manifest_packages "$SRC/manifests/$m.yaml" optional; done | sort -u
    )
    apt-get install -y --no-install-recommends "${extra[@]}"
fi

echo "==> Installing NexusOS packages"
apt-get install -y "$SRC"/debs/nexusos-branding_*.deb "$SRC"/debs/nexusos-defaults_*.deb \
    "$SRC"/debs/nexus-cli_*.deb "$SRC"/debs/nexusos-theme_*.deb "$SRC"/debs/nexusos-desktop_*.deb

echo "==> Default shell configuration for new accounts"
install -m 0644 /usr/share/nexusos/skel/.zshrc /etc/skel/.zshrc

echo "==> Cleaning APT caches in the image"
apt-get clean

echo "==> Done. Verify with: . /etc/os-release && echo \$PRETTY_NAME; nexus version"
