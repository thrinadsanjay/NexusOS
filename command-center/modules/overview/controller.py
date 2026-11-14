"""Overview: the operations dashboard. Real data only; polls only while the page is visible.

Cadence: live values every interval (default 5 s); services, mounts, infrastructure,
certificates, backups and activity every minute; APT updates and sysstat history every
30 minutes or on Refresh. Everything runs as the logged-in user.
"""

from __future__ import annotations

import time
from collections import deque

from nexus_center.base import ModuleController
from nexus_core import activity, dashboard, hardware, metrics, storage
from PySide6.QtCore import Slot

SLOW_S = 60
VERY_SLOW_S = 30 * 60
SPARK_POINTS = 36


def _pct(used: float | None, total: float | None) -> float | None:
    return round(100.0 * used / total, 1) if used is not None and total else None


class Controller(ModuleController):
    poll_interval_ms = 5000

    def __init__(self, tasks, app=None) -> None:
        super().__init__(tasks, app)
        self.sampler = metrics.Sampler()
        self.diskio = dashboard.DiskIo()
        self.sampler.snapshot()  # prime the rate counters: the first refresh already shows CPU/network rates
        self.diskio.rates()
        self.history = dashboard.History()
        self.spark = {k: deque(maxlen=SPARK_POINTS) for k in ("cpu", "memory", "gpu", "disk", "network")}
        self._slow_at = 0.0
        self._very_slow_at = 0.0
        self._in_flight = False
        self._very_slow_running = False
        self._last_live: dict | None = None
        self._slow_cache: dict = {}
        self._very_slow_cache: dict = {}
        import platform

        from nexus_core.release import read_os_release

        rel = read_os_release()
        self.set(
            chartTab="cpu",
            loaded=False,
            system={"hostname": dashboard.hostname(), "os": rel.pretty_name, "kernel": platform.release()},
        )

    # ------------------------------------------------------------------ refresh
    @Slot()
    def refresh(self) -> None:
        now = time.monotonic()
        if now - self._very_slow_at > VERY_SLOW_S and not self._very_slow_running:
            self._refresh_very_slow()  # APT/sysstat in their own task: live values never wait for them
        if self._in_flight:  # never stack refreshes on a busy machine
            return
        self._in_flight = True
        slow = now - self._slow_at > SLOW_S

        def collect() -> dict:
            out: dict = {"live": self._live()}
            if slow:
                out["slow"] = self._slow()
            return out

        def done(result: dict) -> None:
            self._in_flight = False
            if "slow" in result:
                self._slow_at = time.monotonic()
                self._slow_cache = result["slow"]
            self._last_live = result["live"]
            self._publish(result["live"])

        def failed(_m: str, _h: str) -> None:
            self._in_flight = False

        self.run(collect, done, on_error=failed)

    def _refresh_very_slow(self) -> None:
        """APT simulation and sysstat history: separate tasks, each published when ready."""
        self._very_slow_running = True
        self._very_slow_at = time.monotonic()
        pending = {"n": 2}

        def merge(part: dict) -> None:
            self._very_slow_cache = {**self._very_slow_cache, **part}
            pending["n"] -= 1
            if pending["n"] == 0:
                self._very_slow_running = False
            if self._last_live is not None:
                self._publish(self._last_live)

        def updates() -> dict:
            try:
                return {"updates": dashboard.updates_summary(), "updates_error": None}
            except Exception as exc:  # APT missing or simulation failed: shown as unknown
                return {"updates_error": str(exc)}

        self.run(lambda: {"sar": dashboard.sar_history()}, merge, on_error=lambda _m, _h: merge({}))
        self.run(updates, merge, on_error=lambda _m, _h: merge({}))

    @Slot()
    def refreshAll(self) -> None:
        self._slow_at = self._very_slow_at = 0.0
        hardware.inventory(refresh=True)
        self.refresh()

    @Slot(str)
    def setChartTab(self, tab: str) -> None:
        if tab in ("cpu", "memory", "disk", "network"):
            self.set(chartTab=tab, chart=self._chart(tab))

    # ------------------------------------------------------------------ collectors (worker thread)
    def _live(self) -> dict:
        snap = self.sampler.snapshot()
        inv = hardware.inventory()
        io = self.diskio.rates()
        disk_bps = sum(r["read"] + r["write"] for r in io.values()) if io else None
        net_rx = sum(n.rx_bytes_per_s for n in snap.net if n.interface != "lo") if snap.net else None
        net_tx = sum(n.tx_bytes_per_s for n in snap.net if n.interface != "lo") if snap.net else None
        mem_used = (snap.memory_total - snap.memory_available) if snap.memory_total and snap.memory_available else None
        mem_pct = _pct(mem_used, snap.memory_total)
        live_gpus = hardware.gpus(names=False)
        names = {g.pci_slot: g.name for g in inv.gpus}
        for g in live_gpus:
            g.name = names.get(g.pci_slot, g.name)
        gpu = next(iter(live_gpus), None)
        self.history.add(
            time.time(), snap.cpu_percent, mem_pct, disk_bps, (net_rx or 0) + (net_tx or 0) if snap.net else None
        )
        for key, value in (
            ("cpu", snap.cpu_percent),
            ("memory", mem_pct),
            ("gpu", gpu.busy_percent if gpu else None),
            ("disk", disk_bps),
            ("network", (net_rx or 0) + (net_tx or 0) if snap.net else None),
        ):
            if value is not None:
                self.spark[key].append(round(float(value), 2))
        return {
            "snap": snap,
            "inv": inv,
            "gpus": live_gpus,
            "io": io,
            "disk_bps": disk_bps,
            "net": (net_rx, net_tx),
            "mem": (mem_used, mem_pct),
            "cpu_temp": dashboard.cpu_package_temperature(snap.temperatures),
        }

    def _slow(self) -> dict:
        usage = [u for u in storage.usage() if not u.mount.startswith(("/boot", "/snap", "/var/snap"))]
        return {
            "services": dashboard.services_summary(),
            "usage": usage,
            "infra": dashboard.infrastructure(),
            "certs": dashboard.certificates(),
            "backups": dashboard.backups(),
            "activity": activity.recent(8),
            "online": _online(),
        }

    # ------------------------------------------------------------------ publish (UI thread)
    def _publish(self, live: dict) -> None:
        snap, inv = live["snap"], live["inv"]
        slow, very = self._slow_cache, self._very_slow_cache
        usage = slow.get("usage", [])
        root = next((u for u in usage if u.mount == "/"), usage[0] if usage else None)
        updates = very.get("updates")
        mem_used, mem_pct = live["mem"]
        rx, tx = live["net"]
        gpus = live["gpus"]
        gpu = gpus[0] if gpus else None
        worst = max(usage, key=lambda u: u.used / u.size if u.size else 0) if usage else None
        drives = []
        for d in inv.drives:
            mount_usage = next((u for u in usage if u.mount in d.mounts), None)
            rates = live["io"].get(d.name, {})
            drives.append(
                {
                    **d.model_dump(),
                    "usage_mount": mount_usage.mount if mount_usage else None,
                    "usage_percent": _pct(mount_usage.used, mount_usage.size) if mount_usage else None,
                    "read_bps": rates.get("read"),
                    "write_bps": rates.get("write"),
                }
            )
        issues = dashboard.attention(
            services=slow.get("services"),
            updates=updates,
            usage=usage,
            certs=slow.get("certs"),
            backup=slow.get("backups"),
            temperature_c=live["cpu_temp"],
            memory_percent=mem_pct,
        )
        tiles = {
            "cpu": {
                "percent": snap.cpu_percent,
                "perCore": snap.per_cpu_percent,
                "mhz": inv.cpu.current_mhz,
                "temp": live["cpu_temp"],
                "load": list(snap.load) if snap.load else None,
                "spark": list(self.spark["cpu"]),
            },
            "memory": {
                "percent": mem_pct,
                "used": mem_used,
                "total": snap.memory_total,
                "available": snap.memory_available,
                "swapTotal": snap.swap_total,
                "swapUsed": (snap.swap_total - snap.swap_free) if snap.swap_total else None,
                "spark": list(self.spark["memory"]),
            },
            "gpu": {
                "present": gpu is not None,
                "percent": gpu.busy_percent if gpu else None,
                "vramUsed": gpu.vram_used_bytes if gpu else None,
                "vramTotal": gpu.vram_total_bytes if gpu else None,
                "temp": gpu.temperature_c if gpu else None,
                "power": gpu.power_w if gpu else None,
                "powerLimit": gpu.power_limit_w if gpu else None,
                "spark": list(self.spark["gpu"]),
            },
            "storage": {
                "mount": root.mount if root else None,
                "percent": _pct(root.used, root.size) if root else None,
                "free": root.available if root else None,
                "bps": live["disk_bps"],
                "spark": list(self.spark["disk"]),
            },
            "vulnerabilities": {
                "known": updates is not None,
                "count": updates.security if updates else None,
                "packages": updates.security_packages[:12] if updates else [],
            },
            "updates": {
                "known": updates is not None,
                "total": updates.total if updates else None,
                "security": updates.security if updates else None,
                "checked": updates.checked_at if updates else None,
                "error": very.get("updates_error"),
            },
            "network": {"online": slow.get("online"), "rx": rx, "tx": tx, "spark": list(self.spark["network"])},
            "mounts": {
                "count": len(usage),
                "worst": {"mount": worst.mount, "percent": _pct(worst.used, worst.size)} if worst else None,
            },
        }
        state = slow.get("services")
        self.set(
            loaded=True,
            tiles=tiles,
            hardware={"cpu": inv.cpu, "memory": inv.memory, "gpus": gpus, "drives": drives},
            services=state,
            infra=slow.get("infra"),
            certs=slow.get("certs"),
            backups=slow.get("backups"),
            activity=slow.get("activity", []),
            attention=issues,
            health="degraded" if any(i.severity == "critical" for i in issues) else "attention" if issues else "ok",
            uptime=snap.uptime_seconds,
            processes=snap.process_count,
            sar=very.get("sar"),
            chart=self._chart(self._data.get("chartTab", "cpu")),
        )

    def _chart(self, tab: str) -> dict:
        sar = self._very_slow_cache.get("sar")
        if sar is not None and sar.available and sar.points_24h.get(tab):
            return {"source": "sar", "points": sar.points_24h[tab]}
        return {"source": "session", "points": [[t, v] for t, v in self.history.series(tab)]}


def _online() -> bool | None:
    """A default route exists (IPv4 or IPv6)."""
    try:
        with open("/proc/net/route", encoding="utf-8") as f:
            if any(line.split()[1] == "00000000" for line in f.readlines()[1:] if len(line.split()) > 1):
                return True
        with open("/proc/net/ipv6_route", encoding="utf-8") as f:
            return any(line.startswith("00000000000000000000000000000000 00") for line in f)
    except OSError:
        return None
