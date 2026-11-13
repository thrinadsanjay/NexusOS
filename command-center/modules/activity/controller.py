from __future__ import annotations

from nexus_center.base import ModuleController
from nexus_core import activity
from PySide6.QtCore import Slot


class Controller(ModuleController):
    @Slot()
    def refresh(self) -> None:
        query = self._data.get("query", "")
        self.run(lambda: activity.recent(500, query), lambda items: self.set(items=items))

    @Slot(str)
    def filter(self, query: str) -> None:
        self.set(query=query)
        self.refresh()
