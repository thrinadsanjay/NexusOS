"""Operations dashboard data (Command Center Overview, ``nexus system dashboard``).

Everything is collected as the logged-in user. Sources the user cannot read
(Docker without socket access, libvirt without group membership, system logs) are
reported as ``access: false`` rather than guessed. Expensive parts (APT simulation,
sysstat history) are cached by the caller.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from nexus_core import packages, paths, runner
from nexus_core.metrics import PROC, _read

SYSSTAT_DIR = Path("/var/log/sysstat")
BACKUP_EXCLUDE = {"dpkg-db-backup.service"}  # Debian's package-database snapshot, not a user backup
BACKUP_UNIT_RE = re.compile(r"(backup|restic|borg|timeshift|deja-dup|duplicity|rsnapshot|kopia|proxmox-backup)", re.I)
HISTORY_POINTS = 24 * 60  # one-minute buckets, 24 h


# ---------------------------------------------------------------------------- services
class ServiceSummary(BaseModel):
    system_state: str | None = None  # running | degraded | ...
    running: int = 0
    failed: list[str] = []
    starting: int = 0
    total: int = 0


def services_summary() -> ServiceSummary:
    result = runner.run(
        ["systemctl", "list-units", "--type=service", "--all", "--output=json", "--no-pager"], timeout=10
    )
    out = ServiceSummary()
    if result.ok:
        try:
            units = json.loads(result.stdout)
        except ValueError:
            units = []
        for u in units:
            if u.get("load") == "not-found":
                continue
            out.total += 1
            if u.get("active") == "failed":
                out.failed.append(u.get("unit", "?"))
            elif u.get("sub") == "running":
                out.running += 1
            elif u.get("active") in ("activating", "reloading", "deactivating"):
                out.starting += 1
    state = runner.run(["systemctl", "is-system-running"], timeout=5)
    out.system_state = state.stdout.strip() or None
    return out


# ---------------------------------------------------------------------------- updates
class UpdateSummary(BaseModel):
    total: int
    security: int
    security_packages: list[str]
    lists_age_hours: float | None = None
    checked_at: str


def updates_summary() -> UpdateSummary:
    pkgs = packages.simulate_upgrade()
    sec = sorted(p.name for p in pkgs if p.security)
    return UpdateSummary(
        total=len(pkgs),
        security=len(sec),
        security_packages=sec,
        lists_age_hours=packages.apt_lists_age_hours(),
        checked_at=dt.datetime.now().strftime("%H:%M"),
    )


# ---------------------------------------------------------------------------- infrastructure
class InfraSummary(BaseModel):
    docker_access: bool
    containers_running: int | None = None
    containers_total: int | None = None
    libvirt_access: bool
    vms_running: int | None = None
    vms_total: int | None = None
    apps: list[dict] = []


def infrastructure() -> InfraSummary:
    from nexus_core import privilege

    profile = privilege.access()
    out = InfraSummary(docker_access=profile.docker, libvirt_access=profile.libvirt)
    if profile.docker:
        try:
            from nexus_core.docker import DockerClient

            containers = DockerClient().containers(all_containers=True)
            out.containers_total = len(containers)
            out.containers_running = sum(1 for c in containers if c.state == "running")
        except Exception:  # daemon stopped or socket gone: shown as unavailable
            out.docker_access = False
    if profile.libvirt and runner.which("virsh"):
        every = runner.run(["virsh", "-c", "qemu:///system", "list", "--all", "--name"], timeout=10)
        running = runner.run(["virsh", "-c", "qemu:///system", "list", "--state-running", "--name"], timeout=10)
        if every.ok:
            out.vms_total = len([n for n in every.stdout.split() if n])
            out.vms_running = len([n for n in running.stdout.split() if n]) if running.ok else None
    try:
        from nexus_core.apps import lifecycle, registry

        for app_id in lifecycle.installed_ids():
            try:
                out.apps.append({"name": registry.get(app_id).name, "health": lifecycle.health(registry.get(app_id))})
            except Exception:
                out.apps.append({"name": app_id, "health": "unknown"})
    except ImportError:  # application platform not installed
        return out
    return out


# ---------------------------------------------------------------------------- certificates / backups
class CertSummary(BaseModel):
    valid: int = 0
    expiring: int = 0
    expired: int = 0
    next_expiry: str | None = None


def certificates() -> CertSummary:
    from nexus_core.gateway import certs

    out = CertSummary()
    try:
        found = certs.inventory(paths.gateway_dir())
    except Exception:
        return out
    for c in found:
        if c.status == "expired":
            out.expired += 1
        elif c.status in ("warning", "critical"):
            out.expiring += 1
        else:
            out.valid += 1
    upcoming = sorted((c for c in found if c.days_left >= 0), key=lambda c: c.days_left)
    out.next_expiry = f"{upcoming[0].name} in {upcoming[0].days_left} d" if upcoming else None
    return out


class BackupSummary(BaseModel):
    configured: bool
    jobs: list[dict] = []  # {"unit", "last", "next", "result"}
    overdue: bool = False


def _usec(value) -> dt.datetime | None:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return dt.datetime.fromtimestamp(v / 1_000_000) if v > 0 else None


def backups() -> BackupSummary:
    """Backup jobs = systemd timers that look like backups (restic, borg, timeshift, …)."""
    result = runner.run(["systemctl", "list-timers", "--all", "--output=json", "--no-pager"], timeout=10)
    jobs = []
    if result.ok:
        try:
            timers = json.loads(result.stdout)
        except ValueError:
            timers = []
        for t in timers:
            unit = t.get("activates") or t.get("unit") or ""
            if not BACKUP_UNIT_RE.search(unit) or unit in BACKUP_EXCLUDE:
                continue
            last, nxt = _usec(t.get("last")), _usec(t.get("next"))
            res = runner.run(["systemctl", "show", unit, "--property=Result", "--value"], timeout=5).stdout.strip()
            jobs.append(
                {
                    "unit": unit,
                    "last": last.strftime("%d %b %H:%M") if last else None,
                    "next": nxt.strftime("%d %b %H:%M") if nxt else None,
                    "result": res or None,
                    "age_hours": round((dt.datetime.now() - last).total_seconds() / 3600, 1) if last else None,
                }
            )
    overdue = any(j["result"] not in (None, "success") or (j["age_hours"] or 0) > 48 for j in jobs)
    return BackupSummary(configured=bool(jobs), jobs=jobs, overdue=overdue)


# ---------------------------------------------------------------------------- history
@dataclass
class History:
    """Per-minute averages since the Command Center started (24 h ring buffer).

    Used when sysstat is not collecting; with sysstat the 24 h chart comes from ``sar``.
    """

    cpu: deque = field(default_factory=lambda: deque(maxlen=HISTORY_POINTS))
    memory: deque = field(default_factory=lambda: deque(maxlen=HISTORY_POINTS))
    disk: deque = field(default_factory=lambda: deque(maxlen=HISTORY_POINTS))
    network: deque = field(default_factory=lambda: deque(maxlen=HISTORY_POINTS))
    _bucket: dict = field(default_factory=dict)

    def add(
        self, ts: float, cpu: float | None, mem: float | None, disk_bps: float | None, net_bps: float | None
    ) -> None:
        minute = int(ts // 60) * 60
        b = self._bucket
        if b and b["minute"] != minute:
            self._flush()
        if not self._bucket:
            self._bucket = {"minute": minute, "n": 0, "cpu": 0.0, "mem": 0.0, "disk": 0.0, "net": 0.0}
        b = self._bucket
        b["n"] += 1
        b["cpu"] += cpu or 0.0
        b["mem"] += mem or 0.0
        b["disk"] += disk_bps or 0.0
        b["net"] += net_bps or 0.0

    def _flush(self) -> None:
        b, self._bucket = self._bucket, {}
        n = max(b["n"], 1)
        for series, key in ((self.cpu, "cpu"), (self.memory, "mem"), (self.disk, "disk"), (self.network, "net")):
            series.append((b["minute"], round(b[key] / n, 2)))

    def series(self, name: str, include_current: bool = True) -> list[tuple[int, float]]:
        data = list(getattr(self, name))
        b = self._bucket
        if include_current and b:
            key = {"cpu": "cpu", "memory": "mem", "disk": "disk", "network": "net"}[name]
            data.append((b["minute"], round(b[key] / max(b["n"], 1), 2)))
        return data


class DiskIo:
    """Whole-disk read/write rates from /proc/diskstats (sectors are 512 bytes)."""

    def __init__(self) -> None:
        self._last: tuple[float, dict[str, tuple[int, int]]] | None = None

    @staticmethod
    def _read() -> dict[str, tuple[int, int]]:
        out = {}
        for line in (_read(PROC / "diskstats") or "").splitlines():
            p = line.split()
            if len(p) < 10 or not re.match(r"^(nvme\d+n\d+|sd[a-z]+|vd[a-z]+|xvd[a-z]+|mmcblk\d+)$", p[2]):
                continue
            out[p[2]] = (int(p[5]) * 512, int(p[9]) * 512)
        return out

    def rates(self) -> dict[str, dict[str, float]]:
        now, cur = time.monotonic(), self._read()
        rates: dict[str, dict[str, float]] = {}
        if self._last:
            elapsed = max(now - self._last[0], 1e-6)
            for dev, (r, w) in cur.items():
                pr, pw = self._last[1].get(dev, (r, w))
                rates[dev] = {"read": max(r - pr, 0) / elapsed, "write": max(w - pw, 0) / elapsed}
        self._last = (now, cur)
        return rates


class SarHistory(BaseModel):
    available: bool
    reason: str | None = None
    points_24h: dict[str, list[list[float]]] = {}  # name -> [[epoch, value], ...]
    daily: list[dict] = []  # last 7 days: {"day", "cpu", "memory", "disk", "network"}


def _sadf(path: Path, args: list[str]) -> dict | None:
    result = runner.run(["sadf", "-j", str(path), "--", *args], timeout=30, env={"LC_ALL": "C"})
    if not result.ok:
        return None
    try:
        return json.loads(result.stdout)
    except ValueError:
        return None


def _stats(doc: dict | None) -> list[dict]:
    try:
        return doc["sysstat"]["hosts"][0]["statistics"]
    except (KeyError, IndexError, TypeError):
        return []


def _sample_values(s: dict) -> tuple[float | None, float | None, float | None, float | None]:
    cpu = None
    for load in s.get("cpu-load") or s.get("cpu-load-all") or []:
        if load.get("cpu") == "all":
            cpu = round(100.0 - float(load.get("idle", 100.0)), 2)
    mem = (s.get("memory") or {}).get("memused-percent")
    disk = sum(float(d.get("rkB", 0)) + float(d.get("wkB", 0)) for d in s.get("disk") or []) * 1024 or None
    net = sum(
        float(n.get("rxkB", 0)) + float(n.get("txkB", 0))
        for n in (s.get("network") or {}).get("net-dev") or []
        if n.get("iface") != "lo"
    )
    return cpu, (float(mem) if mem is not None else None), disk, (net * 1024 or None)


def _epoch(s: dict) -> float | None:
    ts = s.get("timestamp") or {}
    try:
        stamp = f"{ts['date']} {ts['time']}"
        when = dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
        return (when.replace(tzinfo=dt.UTC) if ts.get("utc") else when).timestamp()
    except (KeyError, ValueError):
        return None


def sar_history(sysstat_dir: Path = SYSSTAT_DIR, days: int = 7) -> SarHistory:
    if not runner.which("sadf"):
        return SarHistory(available=False, reason="sysstat is not installed")
    files = []
    today = dt.date.today()
    for back in range(days):
        day = today - dt.timedelta(days=back)
        for name in (f"sa{day:%Y%m%d}", f"sa{day:%d}"):
            p = sysstat_dir / name
            if p.exists() and p not in [f for _, f in files]:
                files.append((day, p))
                break
    if not files:
        return SarHistory(available=False, reason="sysstat is installed but has not collected data yet")
    args = ["-u", "-r", "-d", "-n", "DEV"]
    cutoff = time.time() - 24 * 3600
    points: dict[str, list[list[float]]] = {"cpu": [], "memory": [], "disk": [], "network": []}
    daily = []
    for day, path in sorted(files):
        stats = _stats(_sadf(path, args))
        if not stats:
            continue
        sums = {"cpu": [], "memory": [], "disk": [], "network": []}
        for s in stats:
            values = dict(zip(("cpu", "memory", "disk", "network"), _sample_values(s), strict=True))
            epoch = _epoch(s)
            for key, v in values.items():
                if v is None:
                    continue
                sums[key].append(v)
                if epoch and epoch >= cutoff:
                    points[key].append([epoch, v])
        daily.append(
            {"day": day.strftime("%a"), **{k: round(sum(v) / len(v), 2) if v else None for k, v in sums.items()}}
        )
    return SarHistory(
        available=bool(daily), points_24h=points, daily=daily, reason=None if daily else "no readable sysstat data"
    )


# ---------------------------------------------------------------------------- attention
class Issue(BaseModel):
    severity: str  # critical | warning | info
    title: str
    detail: str = ""
    page: str = ""  # Command Center module to open
    intent: str = ""


def attention(
    *,
    services: ServiceSummary | None,
    updates: UpdateSummary | None,
    usage: list,
    certs: CertSummary | None,
    backup: BackupSummary | None,
    temperature_c: float | None,
    memory_percent: float | None,
) -> list[Issue]:
    issues: list[Issue] = []
    if services and services.failed:
        names = ", ".join(services.failed[:3]) + (" …" if len(services.failed) > 3 else "")
        issues.append(
            Issue(
                severity="critical",
                title=f"{len(services.failed)} failed service(s)",
                detail=names,
                page="settings",
                intent="native:services",
            )
        )
    if updates and updates.security:
        names = ", ".join(updates.security_packages[:3]) + (" …" if updates.security > 3 else "")
        issues.append(
            Issue(
                severity="warning",
                title=f"{updates.security} security update(s)",
                detail=names,
                page="packages",
                intent="packages.upgrade",
            )
        )
    for u in usage:
        pct = 100 * u.used / u.size if u.size else 0
        if pct >= 90:
            issues.append(
                Issue(
                    severity="critical" if pct >= 97 else "warning",
                    title=f"{u.mount} {pct:.0f} % used",
                    detail=f"{_human(u.available)} free",
                    page="storage",
                )
            )
    if certs and (certs.expired or certs.expiring):
        issues.append(
            Issue(
                severity="critical" if certs.expired else "warning",
                title=f"{certs.expired} expired, {certs.expiring} expiring certificate(s)",
                detail=certs.next_expiry or "",
                page="gateway",
            )
        )
    if backup and backup.overdue:
        issues.append(
            Issue(
                severity="warning",
                title="Backup overdue or failed",
                detail=", ".join(j["unit"] for j in backup.jobs),
                page="settings",
            )
        )
    if temperature_c is not None and temperature_c >= 90:
        issues.append(
            Issue(severity="warning", title=f"CPU at {temperature_c:.0f} °C", detail="check cooling", page="overview")
        )
    if memory_percent is not None and memory_percent >= 92:
        issues.append(
            Issue(
                severity="warning",
                title=f"Memory {memory_percent:.0f} % used",
                detail="see top processes",
                page="overview",
            )
        )
    order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(issues, key=lambda i: order.get(i.severity, 3))


def _human(n: int) -> str:
    for unit, size in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6)):
        if n >= size:
            return f"{n / size:.0f} {unit}" if n >= 10 * size else f"{n / size:.1f} {unit}"
    return f"{n / 1e3:.0f} kB"


def cpu_package_temperature(temps: list) -> float | None:
    """Pick the CPU package sensor (k10temp Tctl/Tdie, coretemp Package) from metrics temperatures."""
    for t in temps:
        label = t.label if hasattr(t, "label") else t.get("label", "")
        value = t.celsius if hasattr(t, "celsius") else t.get("celsius")
        if re.search(r"(k10temp|zenpower) (Tctl|Tdie)|coretemp Package", label):
            return value
    cpu_like = [t for t in temps if re.search(r"k10temp|coretemp|zenpower|cpu", t.label if hasattr(t, "label") else "")]
    return max((t.celsius for t in cpu_like), default=None)


def hostname() -> str:
    return os.uname().nodename
