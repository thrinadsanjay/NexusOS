#!/usr/bin/env bash
# Rebuild Ubuntu's Calamares package with the NexusOS installer patches, in a container.
#
#   scripts/package/build-calamares.sh [--out DIR] [--force]
#
# Takes the calamares source package of the target release (Ubuntu 26.04), adds
# installer/calamares/patches/*.patch to its quilt series, raises the version (+nexusosN) and
# builds the binary packages. Skipped when the patches have not changed since the last build
# (stamp file in the output directory). Only the patches live in this repository, not the
# Calamares sources. Requires Docker; nothing is installed on the host.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="$REPO_ROOT/build/debs"
FORCE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --out) OUT_DIR="$(realpath -m "$2")"; shift 2 ;;
        --force) FORCE=1; shift ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done
mkdir -p "$OUT_DIR"
PATCH_DIR="$REPO_ROOT/installer/calamares/patches"
stamp="$(cat "$PATCH_DIR"/*.patch | sha256sum | cut -c1-16)"
if [ "$FORCE" = 0 ] && [ "$(cat "$OUT_DIR/.calamares-nexusos.stamp" 2>/dev/null)" = "$stamp" ] \
    && ls "$OUT_DIR"/calamares_*nexusos*.deb >/dev/null 2>&1; then
    echo "calamares: NexusOS build is up to date ($stamp)"
    exit 0
fi

proxy_args=()
for var in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY; do
    [ -n "${!var:-}" ] && proxy_args+=(-e "$var")
done
ca_args=()
if [ -n "${NEXUSOS_EXTRA_CA:-}" ] && [ -f "$NEXUSOS_EXTRA_CA" ]; then
    ca_args=(-v "$NEXUSOS_EXTRA_CA:/usr/local/share/ca-certificates/nexusos-extra.crt:ro")
fi

echo "calamares: building with $(ls "$PATCH_DIR"/*.patch | wc -l) NexusOS patch(es) (takes a while)"
rm -f "$OUT_DIR"/calamares_*.deb "$OUT_DIR"/calamares-data_*.deb "$OUT_DIR"/libcalamares*.deb
docker run --rm "${proxy_args[@]}" "${ca_args[@]}" \
    -v "$PATCH_DIR:/patches:ro" -v "$OUT_DIR:/out" -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    ubuntu:26.04 bash -euo pipefail -c '
        export DEBIAN_FRONTEND=noninteractive
        command -v update-ca-certificates >/dev/null && update-ca-certificates >/dev/null 2>&1 || true
        sed -i "s/^Types: deb$/Types: deb deb-src/" /etc/apt/sources.list.d/ubuntu.sources
        apt-get update -qq
        apt-get install -y -qq --no-install-recommends dpkg-dev devscripts quilt >/dev/null
        apt-get build-dep -y -qq calamares >/dev/null
        useradd --create-home builder
        cd /home/builder
        su builder -c "apt-get source -qq calamares >/dev/null"
        src=$(find . -maxdepth 1 -type d -name "calamares-*" | head -1)
        cp /patches/*.patch "$src/debian/patches/"
        for p in /patches/*.patch; do echo "$(basename "$p")" >> "$src/debian/patches/series"; done
        chown -R builder:builder "$src"
        cd "$src"
        version="$(dpkg-parsechangelog -SVersion)+nexusos1"
        su builder -c "DEBFULLNAME=\"NexusOS Maintainers\" DEBEMAIL=maintainers@nexusos.invalid dch -b --newversion $version --distribution resolute \"NexusOS installer patches: default partition layouts (standard and LVM) on the manual page.\""
        su builder -c "QUILT_PATCHES=debian/patches quilt push -a >/dev/null && QUILT_PATCHES=debian/patches quilt pop -a >/dev/null"
        su builder -c "DEB_BUILD_OPTIONS=\"nocheck parallel=$(nproc)\" dpkg-buildpackage -b -uc -us >/tmp/build.log 2>&1" || { tail -60 /tmp/build.log; exit 1; }
        cd ..
        for f in calamares_*.deb calamares-data_*.deb libcalamares*.deb; do [ -f "$f" ] && cp "$f" /out/; done
        rm -f /out/*dbgsym*.deb
        chown -R "$HOST_UID:$HOST_GID" /out
    '
echo "$stamp" > "$OUT_DIR/.calamares-nexusos.stamp"
ls "$OUT_DIR"/calamares_*.deb
