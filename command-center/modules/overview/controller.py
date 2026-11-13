"""Overview: real metrics (no fake data). Polls only while visible, at the user's interval."""

from __future__ import annotations

import time

from nexus_center.base import ModuleController
from nexus_core import metrics, ollama, packages, services, storage
from nexus_core.apps import lifecycle, registry
from nexus_core.store import default_store
from PySide6.QtCore import Slot

WIDGETS = [
    "cpu",
    "memory",
    "temperature",
    "disks",
    "network",
    "gpu",
    "services",
    "updates",
    "apps",
    "processes",
    "system",
]
SLOW_REFRESH_S = 60


class Controller(ModuleController):
    poll_interval_ms = 5000

    def __init__(self, tasks, app=None) -> None:
        super().__init__(tasks, app)
        self.sampler = metrics.Sampler()
        self._slow_at = 0.0
        self._in_flight = False
        visible = default_store().get_setting("overview.widgets", WIDGETS)
        self.set(widgets=WIDGETS, visible=visible, updates=None, updatesChecked=None)

    @Slot()
    def refresh(self) -> None:
        if self._in_flight:  # never stack refreshes if the system is slow
            return
        self._in_flight = True
        slow = time.monotonic() - self._slow_at > SLOW_REFRESH_S

        def collect() -> dict:
            import platform

            from nexus_core.release import read_os_release

            data = {"snapshot": self.sampler.snapshot(), "processes": metrics.top_processes(10)}
            if slow:
                data["gpus"] = metrics.gpus()
                data["usage"] = storage.usage()
                data["services"] = [
                    {"unit": u, "state": services.is_active(u)}
                    for u in (
                        "docker.service",
                        "nginx.service",
                        "ollama.service",
                        "nexusos-agent.socket",
                        "libvirtd.service",
                        "NetworkManager.service",
                    )
                ]
                ai = ollama.ollama_status()
                data["ollama"] = {"reachable": ai.reachable, "version": ai.version, "installed": ai.cli_installed}
                installed = lifecycle.installed_ids()
                apps = []
                for app_id in installed:
                    try:
                        app = registry.get(app_id)
                        apps.append({"name": app.name, "health": lifecycle.health(app)})
                    except Exception:
                        apps.append({"name": app_id, "health": "unknown"})
                data["apps"] = apps
                rel = read_os_release()
                data["system"] = {"os": rel.pretty_name, "build": rel.build_id, "kernel": platform.release()}
            return data

        def done(data: dict) -> None:
            self._in_flight = False
            if slow:
                self._slow_at = time.monotonic()
            self.set(**data)

        def failed(_message: str, _hint: str) -> None:
            self._in_flight = False

        self.run(collect, done, on_error=failed)

    @Slot()
    def checkUpdates(self) -> None:
        self.set(updatesChecking=True)

        def done(plan) -> None:
            self.set(updates=len(plan.changes), updatesChecked=time.strftime("%H:%M"), updatesChecking=False)

        self.run(lambda: packages.plan("upgrade"), done)

    @Slot(str, bool)
    def setWidgetVisible(self, widget: str, visible: bool) -> None:
        current = [w for w in self._data.get("visible", WIDGETS) if w != widget]
        if visible:
            current.append(widget)
        default_store().set_setting("overview.widgets", current)
        self.set(visible=current)
