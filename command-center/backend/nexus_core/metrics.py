"""Real-time system metrics from /proc and /sys (no monitoring daemon, no psutil).

Rates (CPU %, network throughput) are computed from deltas between two samples,
so callers decide the sampling interval; nothing here polls on its own.
Unavailable sensors are reported as ``None`` with a reason, never as fake values.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

PROC = Path(os.environ.get("NEXUSOS_PROC", "/proc"))
SYS = Path(os.environ.get("NEXUSOS_SYS", "/sys"))


class Temperature(BaseModel):
    label: str
    celsius: float


class NetRate(BaseModel):
    interface: str
    rx_bytes_per_s: float
    tx_bytes_per_s: float


class Snapshot(BaseModel):
    cpu_percent: float | None
    per_cpu_percent: list[float] = []
    temperatures: list[Temperature] = []
    temperature_note: str | None = None
    memory_total: int | None = None
    memory_available: int | None = None
    swap_total: int | None = None
    swap_free: int | None = None
    net: list[NetRate] = []
    process_count: int | None = None
    uptime_seconds: float | None = None
    load: tuple[float, float, float] | None = None


@dataclass
class _Sample:
    ts: float
    cpu: list[tuple[int, int]]  # (busy, total) per line: aggregate first
    net: dict[str, tuple[int, int]] = field(default_factory=dict)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _cpu_times() -> list[tuple[int, int]]:
    text = _read(PROC / "stat") or ""
    out = []
    for line in text.splitlines():
        if not line.startswith("cpu"):
            break
        values = [int(v) for v in line.split()[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values[:8])
        out.append((total - idle, total))
    return out


def _net_counters() -> dict[str, tuple[int, int]]:
    text = _read(PROC / "net" / "dev") or ""
    out = {}
    for line in text.splitlines()[2:]:
        name, _, rest = line.partition(":")
        fields = rest.split()
        name = name.strip()
        if name == "lo" or len(fields) < 9:
            continue
        out[name] = (int(fields[0]), int(fields[8]))
    return out


def meminfo() -> dict[str, int]:
    out = {}
    for line in (_read(PROC / "meminfo") or "").splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            out[key] = int(parts[0]) * 1024
    return out


def temperatures() -> tuple[list[Temperature], str | None]:
    """CPU-relevant temperatures from hwmon (k10temp/coretemp/zenpower), else thermal zones."""
    temps: list[Temperature] = []
    hwmon = SYS / "class" / "hwmon"
    preferred = {"k10temp", "coretemp", "zenpower", "cpu_thermal", "nvme", "amdgpu"}
    for dev in sorted(hwmon.glob("hwmon*")) if hwmon.exists() else []:
        name = (_read(dev / "name") or "").strip()
        if name not in preferred:
            continue
        for inp in sorted(dev.glob("temp*_input")):
            raw = _read(inp)
            if not raw or not raw.strip().lstrip("-").isdigit():
                continue
            label = (_read(inp.with_name(inp.name.replace("_input", "_label"))) or inp.name.split("_")[0]).strip()
            temps.append(Temperature(label=f"{name} {label}", celsius=int(raw) / 1000))
    if not temps:
        for zone in sorted((SYS / "class" / "thermal").glob("thermal_zone*")):
            raw = _read(zone / "temp")
            if raw and raw.strip().isdigit():
                temps.append(Temperature(label=(_read(zone / "type") or zone.name).strip(), celsius=int(raw) / 1000))
    note = None if temps else "no temperature sensors exposed (common in VMs and containers)"
    return temps, note


def process_count() -> int:
    return sum(1 for p in PROC.iterdir() if p.name.isdigit()) if PROC.exists() else 0


class Sampler:
    """Computes rates between successive :meth:`snapshot` calls. Cheap: reads a few /proc files."""

    def __init__(self) -> None:
        self._last: _Sample | None = None

    def snapshot(self) -> Snapshot:
        sample = _Sample(time.monotonic(), _cpu_times(), _net_counters())
        cpu_percent: float | None = None
        per_cpu: list[float] = []
        net: list[NetRate] = []
        if self._last and sample.cpu and len(sample.cpu) == len(self._last.cpu):
            rates = []
            for (busy, total), (pbusy, ptotal) in zip(sample.cpu, self._last.cpu, strict=True):
                dt = total - ptotal
                rates.append(round(100.0 * (busy - pbusy) / dt, 1) if dt > 0 else 0.0)
            cpu_percent, per_cpu = rates[0], rates[1:]
            elapsed = max(sample.ts - self._last.ts, 1e-6)
            for name, (rx, tx) in sample.net.items():
                if name in self._last.net:
                    prx, ptx = self._last.net[name]
                    net.append(
                        NetRate(
                            interface=name,
                            rx_bytes_per_s=max(rx - prx, 0) / elapsed,
                            tx_bytes_per_s=max(tx - ptx, 0) / elapsed,
                        )
                    )
        self._last = sample
        mem = meminfo()
        temps, note = temperatures()
        uptime_raw = (_read(PROC / "uptime") or "").split()
        try:
            load = os.getloadavg()
        except OSError:
            load = None
        return Snapshot(
            cpu_percent=cpu_percent,
            per_cpu_percent=per_cpu,
            temperatures=temps,
            temperature_note=note,
            memory_total=mem.get("MemTotal"),
            memory_available=mem.get("MemAvailable"),
            swap_total=mem.get("SwapTotal"),
            swap_free=mem.get("SwapFree"),
            net=net,
            process_count=process_count(),
            uptime_seconds=float(uptime_raw[0]) if uptime_raw else None,
            load=load,
        )
