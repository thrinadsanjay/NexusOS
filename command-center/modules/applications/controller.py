"""Nexus Applications: registry catalogue and Docker Compose lifecycle (nothing auto-installed)."""

from __future__ import annotations

from pathlib import Path

from nexus_center.base import ModuleController
from nexus_core import agent_client
from nexus_core.apps import lifecycle, registry
from PySide6.QtCore import Slot


class Controller(ModuleController):
    def __init__(self, tasks, app=None) -> None:
        super().__init__(tasks, app)
        self.set(apps=[], selected=None, deps=[], logs="", state=None)

    @Slot()
    def refresh(self) -> None:
        def load() -> list:
            return [{"app": a, "state": s} for a, s in lifecycle.catalog()]

        self.run(load, lambda apps: self.set(apps=apps))

    @Slot(str)
    def select(self, app_id: str) -> None:
        def load() -> dict:
            app = registry.get(app_id)
            return {
                "selected": app,
                "deps": lifecycle.check_dependencies(app) if app_id not in lifecycle.installed_ids() else [],
                "state": lifecycle.status(app_id),
            }

        self.run(load, lambda d: self.set(**d))

    def _op(self, label: str, app_id: str, fn) -> None:
        self.run(
            fn,
            lambda _: (self.toast.emit("success", f"{label}: {app_id}"), self.refresh(), self.select(app_id)),
            record=(f"apps.{label}", app_id),
            notify_category="applications",
            label=f"{label} {app_id}",
        )

    @Slot(str)
    def install(self, app_id: str) -> None:
        self._op("install", app_id, lambda: lifecycle.install(app_id))

    @Slot(str, str)
    def action(self, app_id: str, verb: str) -> None:
        self._op(verb, app_id, lambda: lifecycle.action(app_id, verb))

    @Slot(str)
    def update(self, app_id: str) -> None:
        self._op("update", app_id, lambda: lifecycle.update(app_id))

    @Slot(str, bool)
    def uninstall(self, app_id: str, delete_data: bool) -> None:
        self._op("uninstall", app_id, lambda: lifecycle.uninstall(app_id, delete_data))

    @Slot(str)
    def logs(self, app_id: str) -> None:
        self.run(lambda: lifecycle.logs(app_id, 300), lambda t: self.set(logs=t))

    @Slot(str)
    def backup(self, app_id: str) -> None:
        dest = Path.home() / "NexusOS-Backups"
        self.run(
            lambda: str(lifecycle.backup(app_id, dest)),
            lambda path: self.toast.emit("success", f"backup written to {path}"),
            record=("apps.backup", app_id),
            notify_category="backup",
            label=f"backup {app_id}",
        )

    @Slot(str)
    def proposeRoute(self, app_id: str) -> None:
        """Register a *pending* gateway route; the user approves hostname and TLS in the Gateway page."""
        route = lifecycle.suggested_route(registry.get(app_id))
        if route:
            self.run(
                lambda: agent_client.call("gateway.route.save", {"route": route}, label="Save gateway route"),
                lambda _: self.toast.emit("success", f"route {route['hostname']} proposed; approve it in Gateway"),
                record=("gateway.route.propose", route["hostname"]),
            )
