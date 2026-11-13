"""Read-only health checks. Nothing here modifies the system or needs root."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from nexus_cli.core import runner
from nexus_cli.models import HealthCheck, HealthReport
from nexus_cli.services import system
from nexus_cli.services.release import read_os_release

DISK_WARN_PERCENT = 85.0
DISK_FAIL_PERCENT = 95.0
MEMORY_WARN_AVAILABLE_PERCENT = 10.0
REBOOT_REQUIRED_FLAG = Path("/var/run/reboot-required")


def check_os_identity() -> HealthCheck:
    rel = read_os_release()
    if rel.is_nexusos:
        return HealthCheck(name="OS identity", status="ok", detail=rel.pretty_name)
    return HealthCheck(
        name="OS identity",
        status="info",
        detail=f"{rel.pretty_name} (not NexusOS; nexusos-branding not installed)",
    )


def check_disk() -> HealthCheck:
    disks = system.disk_usage()
    if not disks:
        return HealthCheck(name="Disk space", status="skip", detail="no filesystems could be inspected")
    worst = max(disks, key=lambda d: d.used_percent)
    detail = ", ".join(f"{d.mount} {d.used_percent:.0f}% used" for d in disks)
    if worst.used_percent >= DISK_FAIL_PERCENT:
        return HealthCheck(name="Disk space", status="fail", detail=detail, hint="run `nexus system cleanup`")
    if worst.used_percent >= DISK_WARN_PERCENT:
        return HealthCheck(name="Disk space", status="warn", detail=detail, hint="run `nexus system cleanup`")
    return HealthCheck(name="Disk space", status="ok", detail=detail)


def check_memory() -> HealthCheck:
    mem = system.read_meminfo()
    if mem is None:
        return HealthCheck(name="Memory", status="skip", detail="/proc/meminfo unavailable")
    available_pct = 100.0 - mem.used_percent
    detail = f"{system.human_bytes(mem.available_bytes)} available of {system.human_bytes(mem.total_bytes)}"
    status = "warn" if available_pct < MEMORY_WARN_AVAILABLE_PERCENT else "ok"
    return HealthCheck(name="Memory", status=status, detail=detail)


def check_load() -> HealthCheck:
    try:
        one, five, _ = os.getloadavg()
    except OSError:
        return HealthCheck(name="CPU load", status="skip", detail="load average unavailable")
    cpus = os.cpu_count() or 1
    status = "warn" if five > 2 * cpus else "ok"
    return HealthCheck(name="CPU load", status=status, detail=f"1m {one:.2f} / 5m {five:.2f} on {cpus} CPUs")


def check_failed_units() -> HealthCheck:
    if not Path("/run/systemd/system").is_dir():
        return HealthCheck(name="systemd units", status="skip", detail="systemd is not the running init system")
    result = runner.run(["systemctl", "--failed", "--no-legend", "--plain", "--no-pager"])
    if not result.found:
        return HealthCheck(name="systemd units", status="skip", detail="systemctl not found")
    if not result.ok:
        return HealthCheck(
            name="systemd units", status="skip", detail=runner.first_line(result.stderr) or "query failed"
        )
    failed = [line.split()[0] for line in result.stdout.splitlines() if line.strip()]
    if failed:
        return HealthCheck(
            name="systemd units",
            status="fail",
            detail=f"{len(failed)} failed: {', '.join(failed[:5])}",
            hint="inspect with `systemctl status <unit>`",
        )
    return HealthCheck(name="systemd units", status="ok", detail="no failed units")


def check_dpkg() -> HealthCheck:
    result = runner.run(["dpkg", "--audit"], timeout=30)
    if not result.found:
        return HealthCheck(name="Package database", status="skip", detail="dpkg not found")
    if result.stdout.strip():
        return HealthCheck(
            name="Package database",
            status="fail",
            detail="dpkg reports partially installed or broken packages",
            hint="run `sudo dpkg --configure -a` after reviewing `dpkg --audit`",
        )
    return HealthCheck(name="Package database", status="ok", detail="dpkg --audit clean")


def check_reboot_required(flag: Path = REBOOT_REQUIRED_FLAG) -> HealthCheck:
    if flag.exists():
        return HealthCheck(name="Reboot", status="warn", detail="a reboot is required to finish updates")
    return HealthCheck(name="Reboot", status="ok", detail="no reboot pending")


def check_time_sync() -> HealthCheck:
    result = runner.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"])
    if not result.ok:
        return HealthCheck(name="Time sync", status="skip", detail="timedatectl unavailable")
    if result.stdout.strip() == "yes":
        return HealthCheck(name="Time sync", status="ok", detail="clock synchronised")
    return HealthCheck(name="Time sync", status="warn", detail="clock not NTP-synchronised")


ALL_CHECKS: tuple[Callable[[], HealthCheck], ...] = (
    check_os_identity,
    check_disk,
    check_memory,
    check_load,
    check_failed_units,
    check_dpkg,
    check_reboot_required,
    check_time_sync,
)


def run_health_checks(checks: tuple[Callable[[], HealthCheck], ...] = ALL_CHECKS) -> HealthReport:
    results: list[HealthCheck] = []
    for check in checks:
        try:
            results.append(check())
        except Exception as exc:  # a broken check must not hide the others
            results.append(HealthCheck(name=check.__name__, status="skip", detail=f"check error: {exc}"))
    return HealthReport(checks=results)
