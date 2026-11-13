#!/usr/bin/env python3
"""Validate NexusOS Debian packaging metadata, and optionally built .deb contents.

Static checks (packages/*/debian):
  * control: required source/binary fields, Architecture, Maintainer, Standards-Version,
    debhelper-compat 13, Rules-Requires-Root: no, description present
  * changelog: package name and version consistent across packages
  * copyright: DEP-5 header
  * rules executable; maintainer scripts use `set -e` and contain #DEBHELPER#
  * assets.txt sources exist

Artefact checks (``--debs DIR``): each .deb contains its expected installation paths
and has matching control metadata (via dpkg-deb, no installation).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO_ROOT / "packages"
PACKAGES = (
    "nexusos-branding",
    "nexusos-theme",
    "nexus-core",
    "nexusos-management-agent",
    "nexusos-command-center",
    "nexus-cli",
    "nexusos-defaults",
    "nexusos-gateway",
    "nexusos-desktop",
)
# Binary package name when it differs from the source package.
BINARY = {"nexus-core": "python3-nexus-core"}
MAINTAINER_SCRIPTS = ("preinst", "postinst", "prerm", "postrm")
CHANGELOG_RE = re.compile(r"^(?P<name>[a-z0-9.+-]+) \((?P<version>[^)]+)\) (?P<dist>[A-Za-z-]+); urgency=\w+")

EXPECTED_PATHS = {
    "nexusos-branding": [
        "./usr/lib/os-release",
        "./usr/lib/nexusos/release",
        "./usr/share/nexusos/defaults/hostname",
        "./usr/share/nexusos/ascii-logo.txt",
        "./etc/profile.d/nexusos-banner.sh",
        "./etc/xdg/fastfetch/config.jsonc",
        "./usr/share/icons/hicolor/scalable/apps/nexusos.svg",
        "./usr/share/wallpapers/NexusOS/metadata.json",
        "./usr/share/wallpapers/NexusOS/contents/images/1920x1080.png",
        "./usr/share/nexusos/legal/NOTICE",
    ],
    "nexusos-theme": [
        "./usr/share/plasma/look-and-feel/org.nexusos.nexus.desktop/metadata.json",
        "./usr/share/plasma/look-and-feel/org.nexusos.nexus.desktop/contents/defaults",
        "./usr/share/plasma/look-and-feel/org.nexusos.nexus.desktop/contents/layouts/org.kde.plasma.desktop-layout.js",
        "./usr/share/plasma/look-and-feel/org.nexusos.nexus.desktop/contents/previews/preview.png",
        "./usr/share/color-schemes/Nexus.colors",
        "./usr/share/icons/Nexus/index.theme",
        "./usr/share/konsole/Nexus.profile",
        "./usr/share/konsole/Nexus.colorscheme",
    ],
    "nexus-cli": [
        "./usr/bin/nexus",
        "./usr/share/man/man1/nexus.1.gz",
    ],
    "nexusos-defaults": [
        "./usr/share/nexusos/skel/.zshrc",
        "./usr/share/nexusos/shell/nexus-aliases.sh",
        "./usr/share/nexusos/shell/nexus-prompt.zsh",
    ],
    "nexus-core": [
        "./usr/lib/nexusos/nexus-askpass",
    ],
    "nexusos-management-agent": [
        "./usr/share/polkit-1/actions/org.nexusos.agent.policy",
        "./usr/lib/systemd/system/nexusos-agent.socket",
        "./usr/lib/systemd/system/nexusos-agent.service",
    ],
    "nexusos-command-center": [
        "./usr/bin/nexus-center",
        "./usr/share/nexusos-command-center/qml/Main.qml",
        "./usr/share/nexusos-command-center/qml/Nexus/Design/Theme.qml",
        "./usr/share/nexusos-command-center/modules/overview/module.json",
        "./usr/share/nexusos-command-center/modules/packages/controller.py",
        "./usr/share/applications/org.nexusos.CommandCenter.desktop",
        "./usr/share/icons/hicolor/scalable/apps/nexusos-command-center.svg",
    ],
    "nexusos-gateway": [
        "./etc/nginx/conf.d/nexusos-gateway.conf",
        "./usr/share/nexusos/gateway/route.schema.json",
    ],
    "nexusos-desktop": [
        "./usr/share/nexusos/xdg/kdeglobals",
        "./etc/xdg/plasma-workspace/env/nexusos-xdg.sh",
        "./etc/sddm.conf.d/50-nexusos.conf",
        "./usr/share/applications/org.nexusos.ai.desktop",
    ],
}
# Paths that must never be shipped (host-destructive or policy-violating).
FORBIDDEN_PATHS = ("./etc/hostname", "./etc/lsb-release", "./etc/apt/sources.list", "./etc/skel/", "./boot/")


def parse_deb822(text: str) -> list[dict[str, str]]:
    """Minimal deb822 parser: paragraphs of Field: value with continuation lines."""
    paragraphs: list[dict[str, str]] = []
    current: dict[str, str] = {}
    last = None
    for line in text.splitlines():
        if not line.strip():
            if current:
                paragraphs.append(current)
            current, last = {}, None
        elif line[0] in " \t" and last:
            current[last] += "\n" + line.strip()
        elif ":" in line and not line.startswith("#"):
            key, value = line.split(":", 1)
            last = key.strip()
            current[last] = value.strip()
    if current:
        paragraphs.append(current)
    return paragraphs


def check_package(name: str) -> list[str]:
    errors: list[str] = []
    debian = PACKAGES_DIR / name / "debian"
    control_path = debian / "control"
    if not control_path.exists():
        return [f"{name}: debian/control missing"]
    paragraphs = parse_deb822(control_path.read_text(encoding="utf-8"))
    source, binaries = paragraphs[0], paragraphs[1:]
    for field in (
        "Source",
        "Section",
        "Priority",
        "Maintainer",
        "Build-Depends",
        "Standards-Version",
        "Rules-Requires-Root",
    ):
        if field not in source:
            errors.append(f"{name}: control source paragraph lacks {field}")
    if source.get("Source") != name:
        errors.append(f"{name}: Source field is {source.get('Source')!r}")
    if "debhelper-compat (= 13)" not in source.get("Build-Depends", ""):
        errors.append(f"{name}: Build-Depends must include debhelper-compat (= 13)")
    if source.get("Rules-Requires-Root") != "no":
        errors.append(f"{name}: Rules-Requires-Root must be 'no'")
    if not binaries:
        errors.append(f"{name}: no binary package paragraph")
    for binary in binaries:
        for field in ("Package", "Architecture", "Depends", "Description"):
            if field not in binary:
                errors.append(f"{name}: binary {binary.get('Package', '?')} lacks {field}")
        if binary.get("Architecture") not in {"all", "amd64", "any"}:
            errors.append(f"{name}: unexpected Architecture {binary.get('Architecture')}")
        if "\n" not in binary.get("Description", ""):
            errors.append(f"{name}: Description needs an extended description")

    changelog = (debian / "changelog").read_text(encoding="utf-8").splitlines()
    match = CHANGELOG_RE.match(changelog[0]) if changelog else None
    if not match or match["name"] != name:
        errors.append(f"{name}: changelog header malformed or wrong package name")
    if (
        not (debian / "copyright")
        .read_text(encoding="utf-8")
        .startswith("Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/")
    ):
        errors.append(f"{name}: copyright is not DEP-5")
    if (debian / "source" / "format").read_text().strip() != "3.0 (native)":
        errors.append(f"{name}: source format must be 3.0 (native)")
    rules = debian / "rules"
    if not os.access(rules, os.X_OK):
        errors.append(f"{name}: debian/rules is not executable")
    for script in debian.glob("*"):
        if script.name.split(".")[-1] in MAINTAINER_SCRIPTS:
            text = script.read_text(encoding="utf-8")
            if "set -e" not in text:
                errors.append(f"{name}: {script.name} lacks 'set -e'")
            if "#DEBHELPER#" not in text:
                errors.append(f"{name}: {script.name} lacks #DEBHELPER# token")
            for forbidden in ("hostnamectl", "/etc/hostname", "mkfs", "wipefs", "parted", "dd if="):
                if forbidden in text:
                    errors.append(f"{name}: {script.name} contains forbidden operation {forbidden!r}")
    assets = PACKAGES_DIR / name / "assets.txt"
    if assets.exists():
        for line in assets.read_text().splitlines():
            parts = line.split()
            if parts and not parts[0].startswith("#") and not (REPO_ROOT / parts[0]).exists():
                errors.append(f"{name}: assets.txt source missing: {parts[0]}")
    return errors


def changelog_versions() -> dict[str, str]:
    versions = {}
    for name in PACKAGES:
        first = (PACKAGES_DIR / name / "debian" / "changelog").read_text().splitlines()[0]
        match = CHANGELOG_RE.match(first)
        versions[name] = match["version"] if match else "?"
    return versions


def check_debs(deb_dir: Path) -> list[str]:
    errors: list[str] = []
    if shutil.which("dpkg-deb") is None:
        return ["dpkg-deb not available; cannot inspect .deb files"]
    versions = changelog_versions()
    for name in PACKAGES:
        before = len(errors)
        binary = BINARY.get(name, name)
        debs = sorted(deb_dir.glob(f"{binary}_*.deb"))
        if not debs:
            errors.append(f"{name}: no .deb in {deb_dir}")
            continue
        deb = debs[-1]
        fields = subprocess.run(
            ["dpkg-deb", "--field", str(deb), "Package", "Version", "Architecture"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        meta = {k.strip(): v.strip() for k, v in (line.split(":", 1) for line in fields.splitlines() if ":" in line)}
        if meta.get("Package") != binary or meta.get("Version") != versions[name]:
            errors.append(f"{name}: built metadata {meta} does not match changelog {versions[name]}")
        listing = subprocess.run(
            ["dpkg-deb", "--contents", str(deb)], capture_output=True, text=True, check=True
        ).stdout
        paths = {line.split()[-1] if " -> " not in line else line.split()[-3] for line in listing.splitlines()}
        for expected in EXPECTED_PATHS[name]:
            if expected not in paths:
                errors.append(f"{name}: expected path missing from .deb: {expected}")
        for path in paths:
            if any(path.startswith(f) for f in FORBIDDEN_PATHS):
                errors.append(f"{name}: forbidden path shipped: {path}")
        if len(errors) == before:
            print(f"ok   {deb.name}: {len(paths)} paths")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NexusOS Debian packaging.")
    parser.add_argument("--debs", type=Path, help="directory containing built .deb files to inspect")
    args = parser.parse_args(argv)

    errors: list[str] = []
    for name in PACKAGES:
        pkg_errors = check_package(name)
        errors += pkg_errors
        if not pkg_errors:
            print(f"ok   {name}: debian metadata")
    if len(set(changelog_versions().values())) != 1:
        errors.append(f"package versions differ: {changelog_versions()}")
    if args.debs:
        errors += check_debs(args.debs)
    for error in errors:
        print(f"FAIL {error}")
    print("debian: " + ("OK" if not errors else f"{len(errors)} problem(s)"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
