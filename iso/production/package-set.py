#!/usr/bin/env python3
"""Print the package set for the NexusOS image (comma-separated), from the manifests.

usage: package-set.py MANIFEST_DIR NAME [NAME ...]

Takes the mandatory and recommended archive packages of the named manifests (base, desktop),
then adds the NexusOS packages and the live-image tooling. Opt-in manifests (development,
infrastructure, ai) stay installation profiles and are not part of the image.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

LIVE = [
    "casper",  # live session (removed by the installer)
    "calamares-settings-nexusos",  # installer (removed by the installer)
    "grub-pc-bin",  # BIOS installs
    "grub-efi-amd64-bin",  # UEFI installs (signed images come from base)
    "os-prober",
    "language-pack-en",
]
NEXUSOS = ["nexusos-desktop", "plymouth-theme-nexusos"]  # pulls theme, branding, Command Center, CLI, agent


def names(entries) -> list[str]:
    return [e for e in entries or [] if isinstance(e, str)]


def main() -> int:
    root = Path(sys.argv[1])
    out: list[str] = []
    for name in sys.argv[2:]:
        manifest = yaml.safe_load((root / f"{name}.yaml").read_text())
        pkgs = manifest.get("packages", {})
        out += names(pkgs.get("mandatory")) + names(pkgs.get("recommended"))
    out += LIVE + NEXUSOS
    seen: set[str] = set()
    print(",".join(p for p in out if not (p in seen or seen.add(p))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
