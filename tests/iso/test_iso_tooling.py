"""ISO and release tooling: safety guards, checksum generation and read-only inspection."""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT

INSPECT = REPO_ROOT / "scripts/build/inspect-iso.sh"
CHECKSUMS = REPO_ROOT / "scripts/build/checksums.sh"

# Commands that must never be executed by NexusOS tooling (documentation may mention them).
FORBIDDEN = re.compile(r"^\s*(sudo\s+)?(mkfs(\.\w+)?|wipefs|parted|sfdisk|dd\s+[^#]*of=/dev/)\b", re.MULTILINE)


def tooling_files():
    for path in sorted((REPO_ROOT / "scripts").rglob("*")):
        if path.is_file() and path.suffix in {".sh", ".py", ""}:
            yield path
    for path in sorted((REPO_ROOT / "packages").rglob("debian/*")):
        if path.is_file():
            yield path


@pytest.mark.parametrize("path", list(tooling_files()), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_destructive_disk_commands(path):
    if path.resolve() == (REPO_ROOT / "tests/iso/test_iso_tooling.py").resolve():
        return
    assert not FORBIDDEN.search(path.read_text(errors="replace")), f"destructive command in {path}"


def test_inspect_refuses_devices_and_missing_files(tmp_path):
    for target in ("/dev/null", str(tmp_path / "missing.iso")):
        proc = subprocess.run(["bash", str(INSPECT), target], capture_output=True, text=True, check=False)
        assert proc.returncode != 0
        assert "not a regular file" in proc.stderr or "block device" in proc.stderr


@pytest.mark.skipif(shutil.which("xorriso") is None, reason="xorriso not installed")
def test_inspect_synthetic_iso(tmp_path):
    tree = tmp_path / "tree"
    (tree / ".disk").mkdir(parents=True)
    (tree / "casper").mkdir()
    (tree / ".disk" / "info").write_text('NexusOS 1.0 "Engineering Edition" - Development amd64')
    (tree / "casper" / "filesystem.manifest").write_text("nexusos-branding\t0.1.0~dev1\nnexus-cli\t0.1.0~dev1\n")
    iso = tmp_path / "test.iso"
    subprocess.run(["xorriso", "-as", "mkisofs", "-quiet", "-V", "NEXUSOS_TEST", "-o", str(iso), str(tree)], check=True)
    proc = subprocess.run(["bash", str(INSPECT), str(iso)], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "NEXUSOS_TEST" in proc.stdout
    assert "Engineering Edition" in proc.stdout
    assert re.search(r"nexusos-branding\s+0.1.0~dev1", proc.stdout)
    assert re.search(r"nexusos-theme\s+MISSING", proc.stdout)


def test_checksums_generate_and_verify(tmp_path):
    (tmp_path / "a.iso").write_bytes(b"iso-bytes")
    (tmp_path / "b_0.1_all.deb").write_bytes(b"deb-bytes")
    (tmp_path / "notes.txt").write_text("ignored")
    subprocess.run(["bash", str(CHECKSUMS), "generate", str(tmp_path)], check=True, capture_output=True)
    sums = (tmp_path / "SHA256SUMS").read_text()
    assert "a.iso" in sums and "b_0.1_all.deb" in sums and "notes.txt" not in sums
    subprocess.run(["bash", str(CHECKSUMS), "verify", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "a.iso").write_bytes(b"tampered")
    proc = subprocess.run(["bash", str(CHECKSUMS), "verify", str(tmp_path)], capture_output=True, check=False)
    assert proc.returncode != 0


def test_no_production_iso_claimed():
    readme = " ".join((REPO_ROOT / "iso/production/README.md").read_text().lower().split())
    assert "no production iso has been built" in readme
    prototype = " ".join((REPO_ROOT / "iso/prototype/README.md").read_text().lower().split())
    assert "no nexusos iso has been built" in prototype


@pytest.mark.skipif(shutil.which("ischroot") is None, reason="ischroot (debianutils) not installed")
def test_cubic_customisation_refuses_to_run_outside_chroot(tmp_path):
    (tmp_path / "debs").mkdir()
    (tmp_path / "manifests").mkdir()
    proc = subprocess.run(
        ["bash", str(REPO_ROOT / "iso/prototype/customize-chroot.sh"), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        pytest.skip("test environment is itself a chroot")
    assert "must only run inside Cubic's chroot" in proc.stderr
