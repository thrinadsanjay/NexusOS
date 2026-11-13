"""Read-only system information collected from /proc, os-release and the stdlib."""

from __future__ import annotations

import os
import platform
import shutil
import socket
from pathlib import Path

from nexus_core import runner
from nexus_core.log import get_logger
from nexus_core.models import DiskInfo, MemoryInfo, SystemInfo
from nexus_core.release import read_os_release

log = get_logger("system")

PROC = Path("/proc")
DEFAULT_MOUNTS = ("/", "/home", "/var")


def read_meminfo(path: Path = PROC / "meminfo") -> MemoryInfo | None:
    try:
        values: dict[str, int] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            key, _, rest = line.partition(":")
            fields = rest.split()
            if fields and fields[0].isdigit():
                values[key] = int(fields[0]) * 1024  # kB -> bytes
        return MemoryInfo(
            total_bytes=values["MemTotal"],
            available_bytes=values.get("MemAvailable", values.get("MemFree", 0)),
        )
    except (OSError, KeyError) as exc:
        log.debug("meminfo unavailable: %s", exc)
        return None


def read_cpu_model(path: Path = PROC / "cpuinfo") -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine() or "unknown"


def read_uptime(path: Path = PROC / "uptime") -> float | None:
    try:
        return float(path.read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return None


def disk_usage(mounts: tuple[str, ...] = DEFAULT_MOUNTS) -> list[DiskInfo]:
    """Usage for each distinct filesystem among *mounts* (bind duplicates removed)."""
    disks: list[DiskInfo] = []
    seen_devices: set[int] = set()
    for mount in mounts:
        try:
            dev = os.stat(mount).st_dev
            if dev in seen_devices:
                continue
            seen_devices.add(dev)
            usage = shutil.disk_usage(mount)
        except OSError:
            continue
        disks.append(DiskInfo(mount=mount, total_bytes=usage.total, free_bytes=usage.free))
    return disks


def detect_virtualization() -> str | None:
    result = runner.run(["systemd-detect-virt"], timeout=5)
    if result.found:
        value = result.stdout.strip()
        return value or None
    return None


def collect_system_info() -> SystemInfo:
    uname = platform.uname()
    try:
        load = os.getloadavg()
    except OSError:
        load = None
    return SystemInfo(
        hostname=socket.gethostname(),
        os=read_os_release(),
        kernel=uname.release,
        architecture=uname.machine,
        cpu_model=read_cpu_model(),
        cpu_count=os.cpu_count() or 1,
        memory=read_meminfo(),
        disks=disk_usage(),
        uptime_seconds=read_uptime(),
        load_average=load,
        # Only these two well-known, non-secret session variables are reported.
        desktop_session=os.environ.get("XDG_CURRENT_DESKTOP"),
        session_type=os.environ.get("XDG_SESSION_TYPE"),
        virtualization=detect_virtualization(),
    )


def human_bytes(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TiB"


def human_duration(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = [f"{days}d"] if days else []
    parts += [f"{hours}h", f"{minutes}m"]
    return " ".join(parts)
