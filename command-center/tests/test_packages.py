"""Software Center backend: plans, locks, history, repositories, catalogue."""

from __future__ import annotations

import gzip
import os

import pytest
from nexus_core import packages as pk
from nexus_core import runner
from nexus_core.errors import NexusError, ValidationError

SIM = """NOTE: This is only a simulation!
Remv libold1 [1.0-1]
Purg oldconf [2.0]
Inst nginx-common (1.28.3-1 Ubuntu:26.04/resolute [all])
Inst nginx (1.28.3-1 Ubuntu:26.04/resolute [amd64])
Inst libssl3t64 [3.5.0-1] (3.5.0-2 Ubuntu:26.04/resolute-security [amd64])
Conf nginx (1.28.3-1 Ubuntu:26.04/resolute [amd64])
"""


def test_parse_plan_output():
    changes = pk.parse_plan_output(SIM)
    assert [(c.action, c.name) for c in changes] == [
        ("remove", "libold1"),
        ("purge", "oldconf"),
        ("install", "nginx-common"),
        ("install", "nginx"),
        ("upgrade", "libssl3t64"),
    ]


def test_build_command_validates_and_separates_options():
    assert pk.build_command("install", ["nginx"])[-2:] == ["--", "nginx"]
    with pytest.raises(ValidationError):
        pk.build_command("install", ["-oAPT::Get::AllowUnauthenticated=1"])
    assert pk.build_command("update", []) == ["apt-get", "update"]


def _fake_run(stdout="", ok=True, stderr=""):
    def run(args, timeout=0, env=None):
        return runner.CommandResult(tuple(args), 0 if ok else 100, stdout, stderr)

    return run


def test_plan_flags_destructive_and_unrequested_removals(monkeypatch):
    monkeypatch.setattr(pk, "require_apt", lambda: None)
    monkeypatch.setattr(runner, "run", _fake_run(SIM))
    plan = pk.plan("install", ["nginx"])
    assert plan.destructive
    assert any("libold1" in w for w in plan.warnings)
    assert plan.summary["install"] == 2


def test_plan_missing_package(monkeypatch):
    monkeypatch.setattr(pk, "require_apt", lambda: None)
    monkeypatch.setattr(runner, "run", _fake_run(ok=False, stderr="E: Unable to locate package nope"))
    with pytest.raises(NexusError, match="not available"):
        pk.plan("install", ["nope"])


def test_purge_warns_about_configuration(monkeypatch):
    monkeypatch.setattr(pk, "require_apt", lambda: None)
    monkeypatch.setattr(runner, "run", _fake_run("Purg foo [1]\n"))
    plan = pk.plan("purge", ["foo"])
    assert plan.destructive and any("configuration" in w for w in plan.warnings)


def test_lock_status_from_proc_locks(tmp_path, monkeypatch):
    lock = tmp_path / "lock-frontend"
    lock.write_text("")
    st = os.stat(lock)
    monkeypatch.setattr(pk, "DPKG_LOCKS", (lock,))
    locks = tmp_path / "locks"
    locks.write_text(
        f"1: POSIX  ADVISORY  WRITE {os.getpid()} {os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino} 0 EOF\n"
    )
    status = pk.lock_status(locks)
    assert status.locked and status.holder_pid == os.getpid()
    locks.write_text("")
    assert not pk.lock_status(locks).locked


def test_history_parsing(tmp_path, monkeypatch):
    monkeypatch.setattr(pk, "HISTORY_DIR", tmp_path)
    (tmp_path / "history.log").write_text(
        "\nStart-Date: 2026-11-13  10:00:00\nCommandline: apt-get install -y hello\nRequested-By: alice (1000)\n"
        "Install: hello:amd64 (2.10-5)\nEnd-Date: 2026-11-13  10:00:02\n"
    )
    with gzip.open(tmp_path / "history.log.1.gz", "wt") as f:
        f.write("Start-Date: 2026-11-01  09:00:00\nRemove: vim:amd64 (2:9.1)\nEnd-Date: 2026-11-01  09:00:01\n")
    items = pk.history()
    assert items[0].install == ["hello"] and items[0].requested_by.startswith("alice")
    assert items[1].remove == ["vim"]


def test_repositories(tmp_path):
    (tmp_path / "ubuntu.sources").write_text(
        "Types: deb\nURIs: http://archive.ubuntu.com/ubuntu/\nSuites: resolute resolute-updates\n"
        "Components: main universe\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n"
    )
    (tmp_path / "nexusos-tools.sources").write_text(
        "Types: deb\nURIs: https://repo.example.com\nSuites: stable\nEnabled: no\n"
    )
    (tmp_path / "old.list").write_text(
        "deb [signed-by=/etc/apt/keyrings/x.gpg] https://x.example.com/apt stable main\n# deb http://y z\n"
    )
    repos = pk.repositories(tmp_path)
    by_file = {r.file.rsplit("/", 1)[-1]: r for r in repos if r.format == "deb822"}
    assert by_file["ubuntu.sources"].suites == ["resolute", "resolute-updates"]
    assert by_file["nexusos-tools.sources"].managed_by_nexusos and not by_file["nexusos-tools.sources"].enabled
    one_line = [r for r in repos if r.format == "one-line"]
    assert one_line[0].signed_by == "/etc/apt/keyrings/x.gpg" and one_line[1].enabled is False


def test_validate_repository():
    text = pk.validate_repository(
        "tools", "https://repo.example.com/apt", ["stable"], ["main"], "/etc/apt/keyrings/tools.gpg"
    )
    assert "Signed-By: /etc/apt/keyrings/tools.gpg" in text and text.startswith("# Managed by NexusOS")
    for args in [
        ("Tools", "https://a.example.com", ["s"], [], "/etc/apt/keyrings/a.gpg"),
        ("tools", "http://a.example.com", ["s"], [], "/etc/apt/keyrings/a.gpg"),
        ("tools", "https://u:p@a.example.com", ["s"], [], "/etc/apt/keyrings/a.gpg"),
        ("tools", "https://a.example.com", ["s;rm"], [], "/etc/apt/keyrings/a.gpg"),
        ("tools", "https://a.example.com", ["s"], [], "/tmp/evil.gpg"),
        ("tools", "https://a.example.com", [], [], "/etc/apt/keyrings/a.gpg"),
    ]:
        with pytest.raises(ValidationError):
            pk.validate_repository(*args)


def test_catalog_and_search(tmp_path, monkeypatch):
    lists = tmp_path / "lists"
    lists.mkdir()
    (lists / "x_resolute_main_binary-amd64_Packages").write_text(
        "Package: nginx\nSection: httpd\nDescription: small web server\n\n"
        "Package: nginx-doc\nSection: doc\nDescription: docs\n\n"
        "Package: apache2\nSection: httpd\nDescription: web server like nginx\n\n"
    )
    monkeypatch.setattr(pk, "APT_LISTS", lists)
    monkeypatch.setattr(pk, "installed_versions", lambda: {"nginx": "1.28"})
    names = [e.name for e in pk.search("nginx")]
    assert names == ["nginx", "nginx-doc", "apache2"]
    assert pk.search("nginx")[0].installed_version == "1.28"
    assert [e.name for e in pk.search("", section="httpd")] == ["apache2", "nginx"]
    assert dict(pk.sections())["httpd"] == 2
