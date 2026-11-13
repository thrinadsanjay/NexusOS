#!/usr/bin/env bash
# Read-only inspection of a NexusOS (or Ubuntu) live ISO image file.
#
#   scripts/build/inspect-iso.sh [--deep] [--sums SHA256SUMS] IMAGE.iso
#
# Reports: size, checksum (and verification against SHA256SUMS), volume ID, El Torito /
# UEFI boot records, .disk/info, casper layout, package manifest summary and whether
# NexusOS packages are present. With --deep, extracts the root squashfs to a temporary
# directory and reads its os-release (needs several GB of free space).
#
# Safety: the argument must be a regular file. Block devices are refused, nothing is
# mounted, written to the image, or executed from it. Requires xorriso; --deep also
# needs unsquashfs (squashfs-tools).
set -euo pipefail

deep=0; sums=""; iso=""
while [ $# -gt 0 ]; do
    case "$1" in
        --deep) deep=1; shift ;;
        --sums) sums="$2"; shift 2 ;;
        -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
        *) iso="$1"; shift ;;
    esac
done

die() { printf 'inspect-iso: %s\n' "$*" >&2; exit 1; }
[ -n "$iso" ] || die "usage: $0 [--deep] [--sums FILE] IMAGE.iso"
[ -b "$iso" ] && die "refusing to inspect a block device ($iso); pass an image file"
[ -f "$iso" ] || die "not a regular file: $iso"
command -v xorriso >/dev/null || die "xorriso not found (sudo apt install xorriso)"

section() { printf '\n\033[38;2;49;198;189m== %s ==\033[0m\n' "$*"; }
work="$(mktemp -d)"
cleanup() { case "$work" in /tmp/tmp.*) rm -rf -- "$work" ;; esac; }
trap cleanup EXIT

section "Image"
printf 'file:   %s\nsize:   %s bytes\n' "$iso" "$(stat -c %s "$iso")"
sha="$(sha256sum "$iso" | cut -d' ' -f1)"
printf 'sha256: %s\n' "$sha"
if [ -n "$sums" ]; then
    if grep -q "$sha" "$sums"; then echo "checksum: OK (listed in $sums)"; else die "checksum NOT found in $sums"; fi
fi

section "Volume and boot records"
xorriso -indev "$iso" -pvd_info 2>/dev/null | grep -E "Volume Id|Volume Set Id|Publisher Id|Creation Time" || true
xorriso -indev "$iso" -report_el_torito plain 2>/dev/null | grep -E "El Torito|boot img|Boot record" || echo "no El Torito records"
xorriso -indev "$iso" -report_system_area plain 2>/dev/null | grep -E "System area summary|GPT|MBR" | head -5 || true

extract() { xorriso -osirrox on -indev "$iso" -extract "$1" "$2" >/dev/null 2>&1; }

section ".disk/info"
if extract /.disk/info "$work/info"; then cat "$work/info"; echo; else echo "(missing)"; fi

section "Live system layout (/casper)"
xorriso -indev "$iso" -find /casper -maxdepth 1 -type f 2>/dev/null | sed "s/^'//; s/'$//" || echo "(no /casper directory)"

section "Package manifest"
manifest=""
for candidate in /casper/filesystem.manifest /casper/minimal.manifest; do
    if extract "$candidate" "$work/manifest"; then manifest="$work/manifest"; echo "source: $candidate"; break; fi
done
if [ -n "$manifest" ]; then
    printf 'packages: %s\n' "$(wc -l < "$manifest")"
    for pkg in nexusos-branding nexusos-theme nexusos-desktop nexusos-defaults nexus-cli plasma-workspace sddm linux-generic; do
        version="$(awk -v p="$pkg" '$1==p || $1==p":amd64" {print $2}' "$manifest")"
        printf '  %-18s %s\n' "$pkg" "${version:-MISSING}"
    done
    if grep -qiE '^ollama|open-webui' "$manifest"; then echo "WARNING: AI components found in image (policy: post-install only)"; fi
else
    echo "(no manifest found)"
fi

if [ "$deep" -eq 1 ]; then
    section "Root filesystem os-release (deep)"
    command -v unsquashfs >/dev/null || die "unsquashfs not found (sudo apt install squashfs-tools)"
    squash="$(xorriso -indev "$iso" -find /casper -name '*.squashfs' 2>/dev/null | sed "s/^'//; s/'$//" | head -1)"
    [ -n "$squash" ] || die "no squashfs found under /casper"
    extract "$squash" "$work/root.squashfs" || die "could not extract $squash"
    unsquashfs -cat "$work/root.squashfs" usr/lib/os-release 2>/dev/null || echo "(os-release not readable)"
fi
