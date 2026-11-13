#!/usr/bin/env bash
# Render PNG and WebP derivatives of the NexusOS SVG masters for review, docs and the web.
#
#   scripts/build/render-branding.sh [OUT_DIR]      (default: build/branding)
#
# Outputs are build artefacts (git-ignored). Debian packages render their own rasters
# in debian/rules, so this script is only for previews and web use.
# Requires: rsvg-convert (librsvg2-bin); optional: optipng, cwebp (webp).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-$REPO_ROOT/build/branding}"
command -v rsvg-convert >/dev/null || { echo "rsvg-convert not found: sudo apt install librsvg2-bin" >&2; exit 1; }
mkdir -p "$OUT/logo" "$OUT/icons" "$OUT/wallpapers" "$OUT/boot"

render() { # svg width height(optional) out.png
    if [ -n "$3" ]; then rsvg-convert -w "$2" -h "$3" "$1" -o "$4"; else rsvg-convert -w "$2" "$1" -o "$4"; fi
    command -v optipng >/dev/null && optipng -quiet -o2 "$4"
    command -v cwebp >/dev/null && cwebp -quiet -q 90 "$4" -o "${4%.png}.webp"
    return 0
}

for svg in "$REPO_ROOT"/branding/logo/*.svg; do
    render "$svg" 1024 "" "$OUT/logo/$(basename "${svg%.svg}").png"
done
for size in 32 64 128 256 512; do
    render "$REPO_ROOT/branding/icons/nexus-n.svg" "$size" "$size" "$OUT/icons/nexus-n-$size.png"
done
render "$REPO_ROOT/branding/boot/nexusos-boot-logo.svg" 320 "" "$OUT/boot/nexusos-boot-logo.png"
for svg in "$REPO_ROOT"/branding/wallpapers/*.svg; do
    name="$(basename "${svg%.svg}")"
    render "$svg" 3840 2160 "$OUT/wallpapers/$name-3840x2160.png"
    render "$svg" 1920 1080 "$OUT/wallpapers/$name-1920x1080.png"
done
echo "rendered $(find "$OUT" -type f | wc -l) files into $OUT"
