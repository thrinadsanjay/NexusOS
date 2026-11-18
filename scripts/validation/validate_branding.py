#!/usr/bin/env python3
"""Validate NexusOS branding assets and identity metadata.

Checks:
  * design tokens: required colours present and exactly the specified values
  * required SVG masters exist, are well-formed XML with width/height/viewBox,
    carry a licence/attribution comment, and embed no rasters or external references
  * every SVG uses only colours from the design-token palette (plus white/black/none)
  * os-release matches the specified NexusOS identity and keeps Ubuntu compatibility keys
  * generated KDE colour files are in sync with the tokens
  * KDE metadata (look-and-feel, wallpapers) is valid JSON with expected IDs
  * no raster binaries are committed under branding/ or desktop/
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BRANDING = REPO_ROOT / "branding"

SPEC_COLORS = {
    "background-primary": "#0B171B",
    "background-secondary": "#123B40",
    "accent-primary": "#31C6BD",
    "accent-secondary": "#C47750",
    "text-primary": "#E8F1F2",
    "text-secondary": "#9EB3B7",
    "surface": "#142328",
    "surface-elevated": "#1B3036",
    "border": "#29434A",
}

REQUIRED_SVGS = {
    "logo/nexusos-logo.svg": "primary logo",
    "logo/nexusos-logo-horizontal.svg": "horizontal logo",
    "logo/nexusos-logo-mono.svg": "monochrome logo",
    "icons/nexus-n.svg": "geometric N application icon",
    "logo/nexusos-installer-logo.svg": "installer logo",
    "logo/nexusos-terminal-logo.svg": "terminal logo",
    "boot/nexusos-boot-logo.svg": "boot logo",
    "wallpapers/nexusos-default.svg": "default wallpaper",
    "wallpapers/nexusos-abstract.svg": "abstract technology wallpaper",
    "wallpapers/nexusos-engineering.svg": "Engineering Edition wallpaper",
    "icons/nexusos-command-center.svg": "Command Center application icon",
    "icons/nexus-dev.svg": "Nexus Dev launcher icon",
    "icons/nexus-infra.svg": "Nexus Infra launcher icon",
    "icons/nexus-ai.svg": "Nexus AI launcher icon",
    "icons/nexusos-installer.svg": "installer launcher icon",
    "login/nexusos-login-background.svg": "login (SDDM) background",
}

REQUIRED_OS_RELEASE = {
    "NAME": "NexusOS",
    "PRETTY_NAME": "NexusOS Engineering Edition 1.0",
    "ID": "nexusos",
    "ID_LIKE": "ubuntu debian",  # tools (apport, installers) look for debian in ID_LIKE
    "VERSION_ID": "1.0",
    "VERSION": "1.0 LTS",
    "UBUNTU_CODENAME": "resolute",
}

# Colours allowed in artwork besides the core palette: derived tokens and neutrals.
NEUTRALS = {"#FFFFFF", "#FFF", "#000000", "#000"}
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b")
RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


class Report:
    def __init__(self) -> None:
        self.failures = 0

    def ok(self, msg: str) -> None:
        print(f"ok   {msg}")

    def fail(self, msg: str) -> None:
        print(f"FAIL {msg}")
        self.failures += 1


def check_tokens(r: Report) -> set[str]:
    tokens = json.loads((BRANDING / "design-tokens.json").read_text(encoding="utf-8"))
    palette = {v.upper() for v in tokens["color"].values()}
    palette |= {v.upper() for v in tokens["derived"].values() if v.startswith("#")}
    for key, expected in SPEC_COLORS.items():
        actual = tokens["color"].get(key)
        if actual != expected:
            r.fail(f"design token {key} = {actual!r}, expected {expected}")
    if tokens["brand"]["tagline"] != "BUILD. AUTOMATE. DEPLOY.":
        r.fail("brand tagline mismatch")
    r.ok(f"design tokens ({len(tokens['color'])} core colours)")
    return palette


def check_svg(r: Report, rel: str, palette: set[str]) -> None:
    path = BRANDING / rel
    if not path.exists():
        r.fail(f"{rel}: missing ({REQUIRED_SVGS.get(rel, 'asset')})")
        return
    text = path.read_text(encoding="utf-8")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        r.fail(f"{rel}: invalid XML: {exc}")
        return
    if not root.tag.endswith("svg"):
        r.fail(f"{rel}: root element is not <svg>")
    for attr in ("width", "height", "viewBox"):
        if not root.get(attr):
            r.fail(f"{rel}: missing {attr}")
    if "NexusOS contributors" not in text or "GPL-2.0-or-later" not in text:
        r.fail(f"{rel}: missing attribution/licence comment")
    if re.search(r"(xlink:)?href=\"(https?:|data:image)", text) or "<image" in text:
        r.fail(f"{rel}: embeds rasters or external references")
    stray = {c.upper() for c in HEX_RE.findall(text)} - palette - NEUTRALS
    if stray:
        r.fail(f"{rel}: colours outside the design tokens: {sorted(stray)}")
    else:
        r.ok(f"{rel}")


def parse_os_release(path: Path) -> dict[str, str]:
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            data[key] = value.strip().strip('"')
    return data


def check_os_release(r: Report) -> None:
    data = parse_os_release(REPO_ROOT / "configs/os-release/os-release")
    for key, expected in REQUIRED_OS_RELEASE.items():
        if data.get(key) != expected:
            r.fail(f"os-release {key}={data.get(key)!r}, expected {expected!r}")
    if "VERSION_CODENAME" in data and data["VERSION_CODENAME"] != "resolute":
        r.fail("VERSION_CODENAME must stay 'resolute' for APT compatibility")
    release = parse_os_release(REPO_ROOT / "configs/os-release/nexusos-release")
    if release.get("NEXUSOS_RELEASE") != data.get("VERSION_ID"):
        r.fail("nexusos-release NEXUSOS_RELEASE does not match os-release VERSION_ID")
    if release.get("NEXUSOS_BUILD") != data.get("BUILD_ID"):
        r.fail("nexusos-release NEXUSOS_BUILD does not match os-release BUILD_ID")
    r.ok("os-release identity and release metadata")


def check_generated(r: Report) -> None:
    script = REPO_ROOT / "scripts/build/generate_theme_colors.py"
    result = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        r.fail("generated colour files out of date: run scripts/build/generate_theme_colors.py")
    else:
        r.ok("Nexus.colors and Nexus.colorscheme match design tokens")


def check_kde_metadata(r: Report) -> None:
    lnf = json.loads((REPO_ROOT / "desktop/global-theme/org.nexusos.nexus.desktop/metadata.json").read_text())
    if lnf.get("KPackageStructure") != "Plasma/LookAndFeel" or lnf["KPlugin"].get("Id") != "org.nexusos.nexus.desktop":
        r.fail("look-and-feel metadata.json: wrong structure or Id")
    defaults = (REPO_ROOT / "desktop/global-theme/org.nexusos.nexus.desktop/contents/defaults").read_text()
    for needle in ("ColorScheme=Nexus", "Theme=Nexus", "Image=NexusOS"):
        if needle not in defaults:
            r.fail(f"look-and-feel defaults missing {needle}")
    for wp in sorted((REPO_ROOT / "desktop/wallpapers").glob("*/metadata.json")):
        meta = json.loads(wp.read_text())
        if meta.get("KPackageStructure") != "Wallpaper/Images" or meta["KPlugin"].get("Id") != wp.parent.name:
            r.fail(f"{wp.relative_to(REPO_ROOT)}: wrong structure or Id")
    r.ok("KDE look-and-feel and wallpaper metadata")


def check_no_rasters(r: Report) -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "branding", "desktop", "configs"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    ).stdout.split()
    candidates = tracked or [str(p.relative_to(REPO_ROOT)) for p in BRANDING.rglob("*")]
    rasters = [f for f in candidates if Path(f).suffix.lower() in RASTER_SUFFIXES]
    if rasters:
        r.fail(f"raster files committed (render them at build time instead): {rasters}")
    else:
        r.ok("no committed raster derivatives")


def main() -> int:
    r = Report()
    palette = check_tokens(r)
    for rel in REQUIRED_SVGS:
        check_svg(r, rel, palette)
    check_os_release(r)
    check_generated(r)
    check_kde_metadata(r)
    check_no_rasters(r)
    print("branding: " + ("OK" if r.failures == 0 else f"{r.failures} problem(s)"))
    return 1 if r.failures else 0


if __name__ == "__main__":
    sys.exit(main())
