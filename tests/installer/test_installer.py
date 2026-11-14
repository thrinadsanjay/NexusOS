"""Installer (Calamares) and boot (Plymouth, GRUB) configuration invariants."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CAL = ROOT / "installer" / "calamares"


def _yaml(path: Path):
    return yaml.safe_load(path.read_text())


def test_calamares_yaml_parses_and_instances_have_configs():
    settings = _yaml(CAL / "settings.conf")
    shared = {  # shipped by calamares-settings-ubuntu-common-data
        "shellprocess_before_bootloader_kerncopy.conf",
        "before_bootloader_context.conf",
        "shellprocess_logs.conf",
        "shellprocess_bug-LP#1829805.conf",
        "shellprocess_fixconkeys_part1.conf",
        "shellprocess_fixconkeys_part2.conf",
        "shellprocess_rmcdrom.conf",
    }
    for inst in settings["instances"]:
        assert inst["config"] in shared or (CAL / "modules" / inst["config"]).exists(), inst
    for conf in (CAL / "modules").glob("*.conf"):
        _yaml(conf)
    assert settings["branding"] == "nexusos" and (CAL / "branding" / "nexusos" / "branding.desc").exists()


def test_install_sequence_shows_partitioning_before_anything_is_written():
    seq = _yaml(CAL / "settings.conf")["sequence"]
    assert list(seq[0]) == ["show"] and "summary" in seq[0]["show"]
    assert seq[0]["show"].index("partition") < seq[0]["show"].index("summary")
    execs = seq[1]["exec"]
    assert execs[0] == "partition" and execs.index("unpackfs") > execs.index("mount")
    assert "bootloader" in execs and execs[-1] == "umount"


def test_first_account_is_the_sudo_administrator():
    users = _yaml(CAL / "modules" / "users.conf")
    assert users["sudoersGroup"] == "sudo" and "sudo" in users["defaultGroups"] and "adm" in users["defaultGroups"]
    assert users["setRootPassword"] is False and users["allowWeakPasswords"] is False
    assert users["passwordRequirements"]["minLength"] >= 8


def test_encryption_is_offered_and_efi_identity_stays_ubuntu():
    part = _yaml(CAL / "modules" / "partition.conf")
    assert part["enableLuksAutomatedPartitioning"] is True and part["luksGeneration"] == "luks2"
    brand = _yaml(CAL / "branding" / "nexusos" / "branding.desc")
    assert brand["strings"]["bootloaderEntryName"] == "Ubuntu"  # Canonical-signed GRUB looks in /EFI/ubuntu
    grub = (ROOT / "configs" / "grub" / "50-nexusos.cfg").read_text()
    assert 'GRUB_DISTRIBUTOR="Ubuntu"' in grub


def test_installed_system_drops_installer_and_live_tools():
    ops = _yaml(CAL / "modules" / "packages.conf")["operations"]
    removed = next(o["remove"] for o in ops if "remove" in o)
    for pkg in ("calamares", "calamares-settings-nexusos", "casper"):
        assert pkg in removed
    finalize = _yaml(CAL / "modules" / "shellprocess_nexusos_finalize.conf")["script"]
    assert any("userdel" in s["command"] and "nexus-live" in s["command"] for s in finalize)


def test_live_launcher_refuses_outside_the_live_session():
    script = (ROOT / "installer" / "live" / "nexusos-install").read_text()
    assert "boot=casper" in script and "calamares" in script
    helper = (ROOT / "installer" / "live" / "nexusos-live-setup").read_text()
    assert helper.splitlines()[3].startswith('grep -qw "boot=casper"')


def test_plymouth_frames_are_generated(tmp_path):
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "boot/plymouth/generate-frames.py"),
            str(ROOT / "branding/design-tokens.json"),
            str(tmp_path),
            "12",
        ],
        check=True,
    )
    assert len(list(tmp_path.glob("animation-*.svg"))) == 12 == len(list(tmp_path.glob("throbber-*.svg")))
    assert "#31C6BD" in (tmp_path / "animation-0001.svg").read_text()
    theme = (ROOT / "boot/plymouth/nexusos/nexusos.plymouth").read_text()
    assert "ModuleName=two-step" in theme and "ImageDir=/usr/share/plymouth/themes/nexusos" in theme
