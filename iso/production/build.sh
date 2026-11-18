#!/usr/bin/env bash
# Build a NexusOS TEST ISO (not a release) inside a disposable container.
#
#   iso/production/build.sh [--debs DIR] [--out DIR]
#
# Requirements: Docker that can run --privileged containers (the build chroots into the new
# root filesystem and mounts /proc, /sys and /dev inside the container), ~30 GB free disk,
# network access to the Ubuntu archive. The host is not modified: no host disks, devices,
# loop devices or bootloaders are touched; results land in --out (default build/iso).
#
# Boot the result in a VM only (see docs/installation.md). Release ISOs come from a signed,
# reproducible CI pipeline (docs/release-process.md), not from this script.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEB_DIR="$REPO_ROOT/build/debs"
OUT_DIR="$REPO_ROOT/build/iso"
IMAGE="ubuntu:26.04"
while [ $# -gt 0 ]; do
    case "$1" in
        --debs) DEB_DIR="$(realpath "$2")"; shift 2 ;;
        --out) OUT_DIR="$(realpath -m "$2")"; shift 2 ;;
        -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done
for pkg in nexusos-desktop plymouth-theme-nexusos calamares-settings-nexusos nexusos-command-center; do
    ls "$DEB_DIR"/"${pkg}"_*.deb >/dev/null 2>&1 || { echo "missing $pkg in $DEB_DIR (run scripts/package/build-in-container.sh)" >&2; exit 1; }
done
ls "$DEB_DIR"/calamares_*nexusos*.deb >/dev/null 2>&1 || {
    echo "missing the NexusOS Calamares build in $DEB_DIR (run scripts/package/build-calamares.sh)" >&2; exit 1; }
mkdir -p "$OUT_DIR"

# The root filesystem, squashfs and ISO are built inside the container (Docker's data
# directory) and the ISO is written to OUT_DIR: check space before downloading anything.
NEED_GB=${NEXUSOS_ISO_MIN_FREE_GB:-30}
docker_root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)"
for dir in "$docker_root" "$OUT_DIR"; do
    free_gb=$(df -P -B1G "$dir" 2>/dev/null | awk 'NR==2 {print $4}')
    if [ -n "$free_gb" ] && [ "$free_gb" -lt "$NEED_GB" ]; then
        echo "not enough free disk space: ${free_gb} GB free on $(df -P "$dir" | awk 'NR==2 {print $6}') (for $dir), the build needs about ${NEED_GB} GB" >&2
        echo "free space (docker system prune, docker builder prune -af) or enlarge the disk; override with NEXUSOS_ISO_MIN_FREE_GB" >&2
        exit 1
    fi
done

env_args=()
for var in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY NEXUSOS_ARCHIVE NEXUSOS_SECURITY_ARCHIVE NEXUSOS_ISO_NAME; do
    [ -n "${!var:-}" ] && env_args+=(-e "$var")
done
ca_args=()
if [ -n "${NEXUSOS_EXTRA_CA:-}" ] && [ -f "$NEXUSOS_EXTRA_CA" ]; then
    ca_args=(-v "$NEXUSOS_EXTRA_CA:/usr/local/share/ca-certificates/nexusos-extra.crt:ro")
fi

echo "building NexusOS test ISO from $(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'working tree') into $OUT_DIR"
docker run --rm --privileged "${env_args[@]}" "${ca_args[@]}" \
    -v "$REPO_ROOT:/repo:ro" -v "$DEB_DIR:/debs:ro" -v "$OUT_DIR:/out" \
    "$IMAGE" bash /repo/iso/production/build-in-container.sh
