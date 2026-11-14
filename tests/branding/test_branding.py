"""Branding: OS release metadata, version metadata, design tokens and required assets."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from tests.conftest import REPO_ROOT, load_script

validate_branding = load_script("scripts/validation/validate_branding.py")


def test_branding_validator_passes(capsys):
    assert validate_branding.main() == 0, capsys.readouterr().out


@pytest.mark.parametrize(("key", "value"), sorted(validate_branding.REQUIRED_OS_RELEASE.items()))
def test_os_release_identity(key, value):
    data = validate_branding.parse_os_release(REPO_ROOT / "configs/os-release/os-release")
    assert data[key] == value


def test_os_release_keeps_ubuntu_compatibility():
    data = validate_branding.parse_os_release(REPO_ROOT / "configs/os-release/os-release")
    assert data["ID_LIKE"] == "ubuntu"
    assert data["UBUNTU_CODENAME"] == data["VERSION_CODENAME"] == "resolute"
    assert data["DEFAULT_HOSTNAME"] == "nexusos"


def test_version_metadata_consistent():
    os_release = validate_branding.parse_os_release(REPO_ROOT / "configs/os-release/os-release")
    release = validate_branding.parse_os_release(REPO_ROOT / "configs/os-release/nexusos-release")
    assert release["NEXUSOS_RELEASE"] == os_release["VERSION_ID"] == "1.0"
    assert release["NEXUSOS_BUILD"] == os_release["BUILD_ID"] == "0.2.0-dev"
    assert release["NEXUSOS_BASE_CODENAME"] == "resolute"
    cli_init = (REPO_ROOT / "packages/nexus-cli/nexus_cli/__init__.py").read_text()
    assert '__version__ = "0.2.0"' in cli_init


def test_os_release_does_not_claim_to_be_ubuntu():
    text = (REPO_ROOT / "configs/os-release/os-release").read_text()
    assert "\nID=ubuntu\n" not in text
    comments = " ".join(line.lstrip("# ") for line in text.splitlines() if line.startswith("#"))
    assert "not an official Ubuntu product" in comments


def test_attribution_notice():
    notice = (REPO_ROOT / "packages/nexusos-branding/NOTICE").read_text()
    assert "NOT an official Ubuntu product" in notice
    assert "Canonical" in notice


def test_design_tokens_exact_values():
    tokens = json.loads((REPO_ROOT / "branding/design-tokens.json").read_text())
    assert tokens["color"] == validate_branding.SPEC_COLORS
    assert tokens["brand"] == {
        "name": "NexusOS",
        "edition": "Engineering Edition",
        "tagline": "BUILD. AUTOMATE. DEPLOY.",
    }


@pytest.mark.parametrize("rel", sorted(validate_branding.REQUIRED_SVGS))
def test_required_svg_assets(rel):
    path = REPO_ROOT / "branding" / rel
    assert path.is_file()
    root = ET.parse(path).getroot()
    assert root.tag.endswith("svg")
    assert root.get("viewBox")


def test_wallpapers_are_16_by_9():
    for path in (REPO_ROOT / "branding/wallpapers").glob("*.svg"):
        root = ET.parse(path).getroot()
        assert (root.get("width"), root.get("height")) == ("3840", "2160"), path.name


def test_terminal_assets():
    logo = (REPO_ROOT / "configs/shell/ascii-logo.txt").read_text()
    assert 5 <= len(logo.splitlines()) <= 12
    assert max(len(line) for line in logo.splitlines()) <= 40
    banner = (REPO_ROOT / "configs/shell/nexusos-banner.sh").read_text()
    assert "NEXUSOS_NO_BANNER" in banner and ".hushlogin" in banner
    fastfetch = (REPO_ROOT / "configs/shell/fastfetch/config.jsonc").read_text()
    assert "/usr/share/nexusos/ascii-logo.txt" in fastfetch


def test_kde_color_scheme_uses_tokens():
    colors = (REPO_ROOT / "desktop/color-schemes/Nexus.colors").read_text()
    assert "DecorationFocus=49,198,189" in colors  # accent-primary #31C6BD
    assert "[Colors:View]\nBackgroundAlternate=20,35,40\nBackgroundNormal=11,23,27" in colors
    assert "ColorScheme=Nexus" in colors


def test_panel_layout_uses_only_upstream_widgets():
    layout = (REPO_ROOT / "desktop/panels/org.kde.plasma.desktop-layout.js").read_text()
    allowed = {
        "org.kde.plasma.kickoff",
        "org.kde.plasma.pager",
        "org.kde.plasma.panelspacer",
        "org.kde.plasma.systemmonitor.cpu",
        "org.kde.plasma.systemmonitor.memory",
        "org.kde.plasma.systemmonitor.net",
        "org.kde.plasma.digitalclock",
        "org.kde.plasma.systemtray",
        "org.kde.plasma.showdesktop",
        "org.kde.plasma.icontasks",
    }
    import re

    used = set(re.findall(r'addWidget\("([^"]+)"\)', layout))
    assert used <= allowed, used - allowed
    for launcher in ("org.nexusos.dev.desktop", "org.nexusos.infra.desktop", "org.nexusos.ai.desktop"):
        assert launcher in layout
        assert (REPO_ROOT / "packages/nexusos-desktop/applications" / launcher).is_file()


def test_creator_credit_is_consistent():
    """One credit, everywhere it is shown: "Crafted by Sanjay"."""
    release = (REPO_ROOT / "configs/os-release/nexusos-release").read_text()
    assert 'NEXUSOS_CREATOR="Sanjay"' in release
    banner = (REPO_ROOT / "configs/shell/nexusos-banner.sh").read_text()
    assert "NEXUSOS_CREATOR" in banner and "Crafted by" in banner
    assert "Crafted by" in (REPO_ROOT / "configs/shell/fastfetch/config.jsonc").read_text()
    assert "crafted by Sanjay" in (REPO_ROOT / "configs/kde/xdg/kcm-about-distrorc").read_text()
    assert "Sanjay" in (REPO_ROOT / "installer/calamares/branding/nexusos/show.qml").read_text()
    for page in ("packages/nexus-cli/debian/nexus.1", "command-center/frontend/nexus-center.1"):
        assert "crafted by Sanjay" in (REPO_ROOT / page).read_text()
    from nexus_core import release

    assert release.DEFAULT_CREATOR == "Sanjay"
