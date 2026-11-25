#!/usr/bin/env bash
# Build all NexusOS .deb packages inside a disposable Ubuntu 26.04 container.
#
#   scripts/package/build-in-container.sh [--image ubuntu:26.04] [--out DIR] [PACKAGE ...]
#
# This is the reference build: it uses the target release's debhelper, dh-python and
# Python, so results match what an Ubuntu 26.04 builder produces. The repository is
# mounted read-only; the build runs as an unprivileged user inside the container.
# Requires Docker (or Podman with `docker` alias). Nothing is installed on the host.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="ubuntu:26.04"
OUT_DIR="$REPO_ROOT/build/debs"
packages=()

while [ $# -gt 0 ]; do
    case "$1" in
        --image) IMAGE="$2"; shift 2 ;;
        --out) OUT_DIR="$(realpath -m "$2")"; shift 2 ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
        *) packages+=("$1"); shift ;;
    esac
done

command -v docker >/dev/null || { echo "docker not found" >&2; exit 1; }
mkdir -p "$OUT_DIR"

# Forward proxy settings if the host uses them (values are not printed).
proxy_args=()
for var in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY; do
    [ -n "${!var:-}" ] && proxy_args+=(-e "$var")
done
# Optional extra CA bundle for TLS-intercepting proxies.
ca_args=()
if [ -n "${NEXUSOS_EXTRA_CA:-}" ] && [ -f "$NEXUSOS_EXTRA_CA" ]; then
    ca_args=(-v "$NEXUSOS_EXTRA_CA:/usr/local/share/ca-certificates/nexusos-extra.crt:ro")
fi

docker run --rm "${proxy_args[@]}" "${ca_args[@]}" \
    -v "$REPO_ROOT:/src:ro" -v "$OUT_DIR:/out" \
    -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    "$IMAGE" bash -euo pipefail -c '
        export DEBIAN_FRONTEND=noninteractive
        command -v update-ca-certificates >/dev/null && update-ca-certificates >/dev/null 2>&1 || true
        apt-get update -qq
        apt-get install -y -qq --no-install-recommends \
            ca-certificates build-essential dpkg-dev debhelper lintian librsvg2-bin optipng plymouth-theme-spinner fonts-inter fonts-jetbrains-mono \
            dh-python python3-all python3-setuptools pybuild-plugin-pyproject git >/dev/null
        useradd --create-home builder
        cp -a /src /home/builder/nexusos
        rm -rf /home/builder/nexusos/build
        # A checkout on a Windows drive (WSL /mnt/c, /mnt/e) shows every file as executable;
        # use the modes recorded in git so debhelper does not run config files as scripts.
        python3 /home/builder/nexusos/scripts/package/normalize-modes.py /home/builder/nexusos
        chown -R builder:builder /home/builder/nexusos
        su builder -c "NEXUSOS_BUILD_DIR=/home/builder/build /home/builder/nexusos/scripts/package/build-deb.sh --out /home/builder/build/debs $*"
        cp /home/builder/build/debs/* /out/
        chown -R "$HOST_UID:$HOST_GID" /out
    ' bash "${packages[@]}"
echo "packages written to $OUT_DIR"
# The installer needs Calamares with the NexusOS patches (default partition layouts); rebuilt
# only when installer/calamares/patches change. Skip with NEXUSOS_SKIP_CALAMARES=1.
if [ "${#packages[@]}" -eq 0 ] && [ -z "${NEXUSOS_SKIP_CALAMARES:-}" ]; then
    "$REPO_ROOT/scripts/package/build-calamares.sh" --out "$OUT_DIR"
fi
