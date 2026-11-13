"""Debian packaging: control metadata, installation paths and (when possible) real builds."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT, load_script

vd = load_script("scripts/validation/validate_debian.py")

HAVE_DEBHELPER = shutil.which("dpkg-buildpackage") is not None and shutil.which("dh") is not None
BUILT_DEBS = Path(os.environ.get("NEXUSOS_DEB_DIR", REPO_ROOT / "build" / "debs"))


@pytest.mark.parametrize("name", vd.PACKAGES)
def test_debian_metadata(name):
    assert vd.check_package(name) == []


def test_package_versions_aligned():
    assert set(vd.changelog_versions().values()) == {"0.2.0~dev1"}


def test_control_fields():
    control = vd.parse_deb822((REPO_ROOT / "packages/nexusos-branding/debian/control").read_text())
    source, binary = control
    assert source["Source"] == "nexusos-branding"
    assert binary["Architecture"] == "all"
    assert "librsvg2-bin" in source["Build-Depends"]


def test_branding_diversion_scripts_are_symmetric():
    preinst = (REPO_ROOT / "packages/nexusos-branding/debian/nexusos-branding.preinst").read_text()
    postrm = (REPO_ROOT / "packages/nexusos-branding/debian/nexusos-branding.postrm").read_text()
    assert "--add --rename" in preinst and "/usr/lib/os-release.ubuntu" in preinst
    assert "--remove --rename" in postrm and "/usr/lib/os-release.ubuntu" in postrm
    assert "abort-install" in postrm


def test_desktop_package_never_writes_etc_xdg_kdeglobals():
    rules = (REPO_ROOT / "packages/nexusos-desktop/debian/rules").read_text()
    assert "/etc/xdg/kdeglobals" not in rules
    assert "usr/share/nexusos/xdg" in rules


def test_expected_paths_cover_every_package():
    assert set(vd.EXPECTED_PATHS) == set(vd.PACKAGES)


@pytest.mark.skipif(not list(BUILT_DEBS.glob("*.deb")), reason=f"no built packages in {BUILT_DEBS}")
def test_built_debs_contain_expected_paths():
    assert vd.check_debs(BUILT_DEBS) == []


@pytest.mark.slow
@pytest.mark.skipif(not HAVE_DEBHELPER, reason="dpkg-buildpackage/debhelper not installed")
def test_build_nexusos_defaults_package(tmp_path):
    env = {**os.environ, "NEXUSOS_BUILD_DIR": str(tmp_path)}
    proc = subprocess.run(
        [str(REPO_ROOT / "scripts/package/build-deb.sh"), "--no-lintian", "nexusos-defaults"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    debs = list((tmp_path / "debs").glob("nexusos-defaults_*.deb"))
    assert len(debs) == 1
    listing = subprocess.run(
        ["dpkg-deb", "--contents", str(debs[0])], capture_output=True, text=True, check=True
    ).stdout
    assert "./usr/share/nexusos/skel/.zshrc" in listing
    assert "./etc/skel/" not in listing
