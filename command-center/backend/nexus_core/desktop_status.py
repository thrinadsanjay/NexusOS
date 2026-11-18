"""Health, alerts, storage and services for the desktop System Status panel.

``nexus system desktop-status --json`` prints this report; the Plasma widget runs it every few
minutes and when the panel is opened. Live values the desktop already has (CPU, memory, GPU,
disk I/O, network, Bluetooth, battery) come from native Plasma/KDE APIs in the widget, not
from here. Everything is read as the logged-in user. The APT simulation behind the update
counts is cached, so repeated calls stay cheap.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path

from pydantic import BaseModel

from nexus_core import dashboard, storage

UPDATES_TTL_S = 30 * 60
DISK_WARN_PERCENT = 85
DISK_CRITICAL_PERCENT = 95


class MountStatus(BaseModel):
    mount: str
    percent: float
    free: int
    size: int
    level: str  # ok | warning | critical


class ServiceStatus(BaseModel):
    running: int = 0
    failed: int = 0
    failed_units: list[str] = []
    warnings: int = 0  # units starting, stopping or reloading
    state: str | None = None


class UpdateStatus(BaseModel):
    known: bool = False
    total: int = 0
    security: int = 0
    regular: int = 0
    security_packages: list[str] = []
    checked: str | None = None
    error: str | None = None


class DesktopStatus(BaseModel):
    generated: str
    services: ServiceStatus
    updates: UpdateStatus
    root: MountStatus | None
    mounts: list[MountStatus]
    alerts: list[dashboard.Issue]
    counts: dict[str, int]  # critical / warning totals for the rail badge


def _cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    path = (Path(base) if base and os.path.isabs(base) else Path.home() / ".cache") / "nexusos"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def _level(percent: float) -> str:
    return "critical" if percent >= DISK_CRITICAL_PERCENT else "warning" if percent >= DISK_WARN_PERCENT else "ok"


def mounts_status(usage: list[storage.Usage]) -> list[MountStatus]:
    out = []
    for u in usage:
        if not u.size:
            continue
        pct = round(100 * u.used / u.size, 1)
        out.append(MountStatus(mount=u.mount, percent=pct, free=u.available, size=u.size, level=_level(pct)))
    return out


def cached_updates(now: float | None = None, ttl: int = UPDATES_TTL_S) -> dashboard.UpdateSummary | None:
    """APT update summary, recomputed at most every *ttl* seconds (simulation takes seconds)."""
    now = now or time.time()
    cache = _cache_dir() / "desktop-updates.json"
    try:
        doc = json.loads(cache.read_text())
        if now - float(doc.get("at", 0)) < ttl:
            return dashboard.UpdateSummary(**doc["summary"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    summary = dashboard.updates_summary()
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps({"at": now, "summary": summary.model_dump()}))
    tmp.replace(cache)
    return summary


def collect(*, include_updates: bool = True) -> DesktopStatus:
    svc = dashboard.services_summary()
    services = ServiceStatus(
        running=svc.running,
        failed=len(svc.failed),
        failed_units=svc.failed[:10],
        warnings=svc.starting,
        state=svc.system_state,
    )
    updates = UpdateStatus()
    summary = None
    if include_updates:
        try:
            summary = cached_updates()
            updates = UpdateStatus(
                known=True,
                total=summary.total,
                security=summary.security,
                regular=summary.total - summary.security,
                security_packages=summary.security_packages[:10],
                checked=summary.checked_at,
            )
        except Exception as exc:  # APT locked or unavailable: report, do not guess
            updates = UpdateStatus(error=str(exc).splitlines()[0][:120] if str(exc) else type(exc).__name__)
    usage = storage.usage()
    mounts = mounts_status(usage)
    root = next((m for m in mounts if m.mount == "/"), mounts[0] if mounts else None)
    alerts = dashboard.attention(
        services=svc,
        updates=summary,
        usage=usage,
        certs=None,
        backup=None,
        temperature_c=None,
        memory_percent=None,
    )
    counts = {
        "critical": sum(1 for a in alerts if a.severity == "critical"),
        "warning": sum(1 for a in alerts if a.severity == "warning"),
    }
    return DesktopStatus(
        generated=dt.datetime.now().isoformat(timespec="seconds"),
        services=services,
        updates=updates,
        root=root,
        mounts=mounts,
        alerts=alerts,
        counts=counts,
    )
