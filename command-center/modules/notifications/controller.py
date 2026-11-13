from __future__ import annotations

from nexus_center.base import ModuleController
from nexus_core import notifications
from PySide6.QtCore import Slot


class Controller(ModuleController):
    @Slot()
    def refresh(self) -> None:
        def load() -> dict:
            return {
                "items": notifications.list_notifications(include_dismissed=self._data.get("all", False)),
                "prefs": [{"category": k, "enabled": v} for k, v in notifications.preferences().items()],
            }

        self.run(load, lambda d: (self.set(**d), self.app.refreshUnread() if self.app else None))

    @Slot(bool)
    def showAll(self, value: bool) -> None:
        self.set(all=value)
        self.refresh()

    @Slot(int)
    def dismiss(self, nid: int) -> None:
        notifications.dismiss(nid if nid >= 0 else None)
        self.refresh()

    @Slot(str, bool)
    def setPreference(self, category: str, enabled: bool) -> None:
        notifications.set_preference(category, enabled)
        self.refresh()
