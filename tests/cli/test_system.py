"""``nexus system`` commands: info, health, update and cleanup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nexus_core import cleanup, health, packages, system
from nexus_core.models import DiskInfo, HealthCheck, HealthReport, UpgradablePackage

from nexus_cli.commands import system as system_cmd


def test_system_info_json_reports_real_values(cli):
    result = cli("system", "info", "--json")
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["hostname"]
    assert data["cpu_count"] >= 1
    assert data["kernel"]
    assert data["memory"]["total_bytes"] > 0
    assert any(d["mount"] == "/" for d in data["disks"])


def test_system_info_table(cli):
    result = cli("system", "info")
    assert result.exit_code == 0
    for label in ("Hostname", "Kernel", "CPU", "Memory"):
        assert label in result.output


def test_system_info_never_prints_environment(cli, monkeypatch):
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "hunter2-secret")
    for args in (("system", "info"), ("system", "info", "--json"), ("system", "health", "--json")):
        result = cli(*args)
        assert "hunter2-secret" not in result.output


def test_meminfo_parsing(tmp_path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       16000000 kB\nMemFree:  1000 kB\nMemAvailable:   8000000 kB\n")
    mem = system.read_meminfo(meminfo)
    assert mem.total_bytes == 16000000 * 1024
    assert mem.used_percent == 50.0
    assert system.read_meminfo(tmp_path / "missing") is None


def test_human_formatting():
    assert system.human_bytes(512) == "512 B"
    assert system.human_bytes(1536) == "1.5 KiB"
    assert system.human_bytes(None) == "n/a"
    assert system.human_duration(90061) == "1d 1h 1m"


def test_health_checks_are_read_only_and_complete(cli):
    result = cli("system", "health", "--json")
    assert result.exit_code in (0, 1)
    data = json.loads(result.output)
    names = {c["name"] for c in data["checks"]}
    assert {"Disk space", "Memory", "CPU load", "Package database", "Reboot"} <= names
    assert all(c["status"] in {"ok", "warn", "fail", "skip", "info"} for c in data["checks"])


def test_health_exit_code_on_failure(cli, monkeypatch):
    report = HealthReport(checks=[HealthCheck(name="x", status="fail", detail="broken")])
    monkeypatch.setattr(system_cmd.health_service, "run_health_checks", lambda: report)
    result = cli("system", "health")
    assert result.exit_code == 1
    assert "broken" in result.output


def test_health_check_error_is_isolated():
    def boom() -> HealthCheck:
        raise RuntimeError("kaboom")

    report = health.run_health_checks((boom, health.check_memory))
    assert report.checks[0].status == "skip" and "kaboom" in report.checks[0].detail
    assert len(report.checks) == 2


@pytest.mark.parametrize(("used", "expected"), [(50, "ok"), (90, "warn"), (97, "fail")])
def test_disk_thresholds(monkeypatch, used, expected):
    total = 1000
    monkeypatch.setattr(
        health.system, "disk_usage", lambda: [DiskInfo(mount="/", total_bytes=total, free_bytes=total - used * 10)]
    )
    assert health.check_disk().status == expected


def test_reboot_required_flag(tmp_path):
    flag = tmp_path / "reboot-required"
    assert health.check_reboot_required(flag).status == "ok"
    flag.touch()
    assert health.check_reboot_required(flag).status == "warn"


def test_health_degrades_without_programs(no_programs):
    assert health.check_dpkg().status == "skip"
    assert health.check_time_sync().status == "skip"


APT_SIMULATION = """\
NOTE: This is only a simulation!
Reading package lists...
Inst libssl3t64 [3.5.0-1ubuntu1] (3.5.0-1ubuntu2 Ubuntu:26.04/resolute-updates, Ubuntu:26.04/resolute-security [amd64])
Inst newpkg (1.0-1 Ubuntu:26.04/resolute [amd64])
Conf libssl3t64 (3.5.0-1ubuntu2 Ubuntu:26.04/resolute-updates [amd64])
"""


def test_parse_apt_simulation():
    pkgs = packages.parse_simulation(APT_SIMULATION)
    assert [p.name for p in pkgs] == ["libssl3t64", "newpkg"]
    assert pkgs[0].current_version == "3.5.0-1ubuntu1"
    assert pkgs[0].candidate_version == "3.5.0-1ubuntu2"
    assert pkgs[0].origin == "Ubuntu:26.04/resolute-updates"
    assert pkgs[1].current_version is None


def test_update_without_apt_reports_missing_dependency(cli, no_programs):
    result = cli("system", "update", "--dry-run")
    assert result.exit_code == 3
    assert "apt-get not found" in result.output


def test_update_requires_confirmation_and_never_runs_sudo_without_tty(cli, monkeypatch):
    monkeypatch.setattr(packages, "require_apt", lambda: None)
    monkeypatch.setattr(packages, "apt_lists_age_hours", lambda: 1.0)
    monkeypatch.setattr(
        packages,
        "simulate_upgrade",
        lambda: [UpgradablePackage(name="foo", current_version="1", candidate_version="2")],
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(system_cmd.runner, "run_interactive", lambda cmd, **kw: calls.append(cmd) or 0)

    preview = cli("system", "update", "--dry-run")
    assert preview.exit_code == 0 and "foo" in preview.output and not calls

    result = cli("system", "update", input="y\n")  # CliRunner stdin is not a TTY
    assert result.exit_code == 4
    assert calls == []


def test_update_up_to_date(cli, monkeypatch):
    monkeypatch.setattr(packages, "require_apt", lambda: None)
    monkeypatch.setattr(packages, "apt_lists_age_hours", lambda: None)
    monkeypatch.setattr(packages, "simulate_upgrade", list)
    result = cli("system", "update")
    assert result.exit_code == 0 and "up to date" in result.output


def test_cleanup_preview_is_default(cli, monkeypatch, tmp_path):
    cache = tmp_path / ".cache" / "pip"
    cache.mkdir(parents=True)
    (cache / "blob").write_bytes(b"x" * 2048)
    monkeypatch.setattr(cleanup.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(cleanup, "simulate_autoremove_count", lambda: None)
    result = cli("system", "cleanup", "--json")
    assert result.exit_code == 0
    items = {i["id"]: i for i in json.loads(result.output)}
    assert items["pip-cache"]["reclaimable_bytes"] == 2048
    assert (cache / "blob").exists(), "preview must not delete anything"


def test_clean_user_path_only_inside_home(tmp_path):
    home = tmp_path / "home"
    target = home / ".cache" / "thumbnails"
    (target / "sub").mkdir(parents=True)
    (target / "sub" / "a.png").write_bytes(b"1234")
    (target / "b.png").write_bytes(b"12")
    freed = cleanup.clean_user_path(target, home=home)
    assert freed == 6
    assert target.exists() and not any(target.iterdir())

    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(ValueError):
        cleanup.clean_user_path(outside, home=home)


def test_clean_user_path_refuses_symlink(tmp_path):
    home = tmp_path / "home"
    real = tmp_path / "real"
    real.mkdir()
    (home / ".cache").mkdir(parents=True)
    link = home / ".cache" / "pip"
    link.symlink_to(real)
    with pytest.raises(ValueError):
        cleanup.clean_user_path(Path(link), home=home)
