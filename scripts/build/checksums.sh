#!/usr/bin/env bash
# Generate or verify SHA256SUMS/SHA512SUMS for release artefacts (ISOs, .debs).
#
#   scripts/build/checksums.sh generate DIR   -> DIR/SHA256SUMS, DIR/SHA512SUMS
#   scripts/build/checksums.sh verify DIR     -> exit 1 on any mismatch
#
# Only regular files directly inside DIR with artefact extensions are included.
set -euo pipefail

mode="${1:-}"; dir="${2:-}"
if [ -z "$mode" ] || [ ! -d "$dir" ]; then sed -n '2,7p' "$0"; exit 2; fi
cd "$dir"

case "$mode" in
    generate)
        mapfile -t files < <(find . -maxdepth 1 -type f \( -name '*.iso' -o -name '*.deb' -o -name '*.img' -o -name '*.tar.*' \) \
            -printf '%f\n' | LC_ALL=C sort)
        [ ${#files[@]} -gt 0 ] || { echo "no artefacts in $dir" >&2; exit 1; }
        sha256sum -- "${files[@]}" > SHA256SUMS
        sha512sum -- "${files[@]}" > SHA512SUMS
        echo "wrote SHA256SUMS and SHA512SUMS for ${#files[@]} file(s)"
        ;;
    verify)
        sha256sum --check --strict SHA256SUMS
        [ ! -f SHA512SUMS ] || sha512sum --check --strict SHA512SUMS
        ;;
    *) echo "unknown mode: $mode" >&2; exit 2 ;;
esac
