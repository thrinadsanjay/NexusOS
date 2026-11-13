"""System Settings: native hostname/time/services + KDE modules for mature desktop settings."""

from __future__ import annotations

from nexus_center.base import ModuleController
from nexus_core import services, settings
from PySide6.QtCore import Slot


class Controller(ModuleController):
    def __init__(self, tasks, app=None) -> None:
        super().__init__(tasks, app)
        categories: dict[str, list] = {}
        for entry in settings.CATALOG:
            categories.setdefault(entry.category, []).append(entry)
        self.set(categories=[{"name": k, "entries": v} for k, v in categories.items()], units=[], logs="", timezones=[])

    @Slot()
    def refresh(self) -> None:
        def load() -> dict:
            return {
                "hostname": settings.hostname(),
                "time": settings.time_status(),
                "locale": settings.locale_status(),
                "users": settings.users(),
            }

        self.run(load, lambda d: self.set(**d))

    @Slot(str)
    def openKcm(self, kcm: str) -> None:
        self.run(lambda: settings.open_kcm(kcm), lambda _: None)

    @Slot(str)
    def setHostname(self, name: str) -> None:
        self.run(
            lambda: settings.set_hostname(name),
            lambda _: (self.toast.emit("success", "hostname changed"), self.refresh()),
            record=("settings.hostname", name),
        )

    @Slot()
    def loadTimezones(self) -> None:
        self.run(settings.timezones, lambda tz: self.set(timezones=tz))

    @Slot(str)
    def setTimezone(self, tz: str) -> None:
        self.run(lambda: settings.set_timezone(tz), lambda _: self.refresh(), record=("settings.timezone", tz))

    @Slot(bool)
    def setNtp(self, enabled: bool) -> None:
        self.run(lambda: settings.set_ntp(enabled), lambda _: self.refresh(), record=("settings.ntp", str(enabled)))

    @Slot()
    def loadUnits(self) -> None:
        self.run(services.list_units, lambda u: self.set(units=u))

    @Slot(str, str)
    def control(self, unit: str, action: str) -> None:
        self.run(
            lambda: services.control(unit, action),
            lambda _: (self.toast.emit("success", f"{unit}: {action}"), self.loadUnits()),
            record=(f"service.{action}", unit),
            notify_category="operations",
            label=f"{action} {unit}",
        )

    @Slot(str)
    def loadLogs(self, unit: str) -> None:
        self.run(lambda: services.logs(unit, 300), lambda text: self.set(logs=text))

    @Slot(bool)
    def setDark(self, dark: bool) -> None:
        if self.app is not None:
            self.app.dark = dark

    @Slot(int)
    def setInterval(self, ms: int) -> None:
        if self.app is not None:
            self.app.monitoringInterval = ms
