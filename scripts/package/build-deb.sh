#!/usr/bin/env bash
# Build NexusOS Debian packages in a disposable staging tree.
#
#   scripts/package/build-deb.sh [--out DIR] [--no-lintian] [PACKAGE ...]
#
# For each package in packages/<name>/ the script:
#   1. copies the package directory into build/pkgsrc/<name>/ (never builds in Git's tree),
#   2. copies the repository assets listed in packages/<name>/assets.txt into it,
#   3. checks build dependencies (dpkg-checkbuilddeps) and reports what is missing,
#   4. runs `dpkg-buildpackage -b -us -uc` as the current, unprivileged user,
#   5. moves the resulting .deb/.buildinfo/.changes files into build/debs/ (or --out),
#   6. runs lintian when available.
#
# Nothing is installed and no root privileges are used.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="${NEXUSOS_BUILD_DIR:-$REPO_ROOT/build}"
OUT_DIR="$BUILD_DIR/debs"
RUN_LINTIAN=1
ALL_PACKAGES=(nexusos-branding nexusos-theme nexus-core nexusos-management-agent nexusos-command-center nexus-cli nexusos-defaults nexusos-gateway nexusos-desktop plymouth-theme-nexusos calamares-settings-nexusos)

die() { printf 'build-deb: error: %s\n' "$*" >&2; exit 1; }
log() { printf '\033[38;2;49;198;189m==>\033[0m %s\n' "$*"; }

packages=()
while [ $# -gt 0 ]; do
    case "$1" in
        --out) OUT_DIR="$(realpath -m "$2")"; shift 2 ;;
        --no-lintian) RUN_LINTIAN=0; shift ;;
        -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
        -*) die "unknown option $1" ;;
        *) packages+=("$1"); shift ;;
    esac
done
[ ${#packages[@]} -eq 0 ] && packages=("${ALL_PACKAGES[@]}")

command -v dpkg-buildpackage >/dev/null || die "dpkg-buildpackage not found (apt install dpkg-dev debhelper)"
[ "$(id -u)" -eq 0 ] && log "warning: running as root is not required; prefer an unprivileged user"

STAGE_ROOT="$BUILD_DIR/pkgsrc"
mkdir -p "$STAGE_ROOT" "$OUT_DIR"

binaries() { # binary package names declared in a source package's debian/control
    sed -n 's/^Package: *//p' "$1/debian/control"
}

copy_asset() {
    local from="$1" to="$2" stage="$3"
    case "$from$to" in
        *..*|/*) die "unsafe asset path: $from -> $to" ;;
    esac
    [ -e "$REPO_ROOT/$from" ] || die "asset not found: $from"
    mkdir -p "$(dirname "$stage/$to")"
    cp -a "$REPO_ROOT/$from" "$stage/$to"
}

build_one() {
    local pkg="$1"
    local src="$REPO_ROOT/packages/$pkg"
    local stage="$STAGE_ROOT/$pkg"
    [ -f "$src/debian/control" ] || die "no debian/control for $pkg"

    log "staging $pkg"
    # Only ever clear our own staging directory.
    case "$stage" in "$STAGE_ROOT"/?*) ;; *) die "refusing to clean $stage" ;; esac
    rm -rf -- "$stage"
    mkdir -p "$stage"
    tar -C "$src" --exclude='__pycache__' --exclude='*.egg-info' --exclude='assets.txt' -cf - . | tar -C "$stage" -xf -

    if [ -f "$src/assets.txt" ]; then
        while read -r from to _; do
            case "$from" in ''|'#'*) continue ;; esac
            [ -n "$to" ] || die "assets.txt line for $from has no destination"
            copy_asset "$from" "$to" "$stage"
        done < "$src/assets.txt"
    fi

    if ! (cd "$stage" && dpkg-checkbuilddeps 2>"$STAGE_ROOT/$pkg.builddeps.log"); then
        cat "$STAGE_ROOT/$pkg.builddeps.log" >&2
        die "missing build dependencies for $pkg (install them with apt, then retry)"
    fi

    log "building $pkg"
    (cd "$stage" && dpkg-buildpackage -b -us -uc --no-sign >"$STAGE_ROOT/$pkg.build.log" 2>&1) || {
        tail -n 40 "$STAGE_ROOT/$pkg.build.log" >&2
        die "build failed for $pkg (full log: $STAGE_ROOT/$pkg.build.log)"
    }
    find "$STAGE_ROOT" -maxdepth 1 -type f \( -name "${pkg}_*.buildinfo" -o -name "${pkg}_*.changes" \) \
        -exec mv -f {} "$OUT_DIR/" \;
    for bin in $(binaries "$src"); do
        find "$STAGE_ROOT" -maxdepth 1 -type f -name "${bin}_*.deb" -exec mv -f {} "$OUT_DIR/" \;
        log "built $(cd "$OUT_DIR" && ls "${bin}"_*.deb)"
    done
}

for pkg in "${packages[@]}"; do
    build_one "$pkg"
done

if [ "$RUN_LINTIAN" -eq 1 ] && command -v lintian >/dev/null; then
    log "lintian"
    for pkg in "${packages[@]}"; do
        for bin in $(binaries "$REPO_ROOT/packages/$pkg"); do
            lintian --fail-on error --display-info --suppress-tags-from-file "$REPO_ROOT/packages/lintian-overrides.txt" \
                "$OUT_DIR/${bin}"_*.deb || die "lintian errors in $bin"
        done
    done
fi
log "packages in $OUT_DIR"
