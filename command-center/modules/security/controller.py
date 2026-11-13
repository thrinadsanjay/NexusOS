from __future__ import annotations

from nexus_center.base import ModuleController
from nexus_core import security
from PySide6.QtCore import Slot


class Controller(ModuleController):
    @Slot()
    def refresh(self) -> None:
        self.run(lambda: {"checks": security.overview(), "ports": security.listening_ports()}, lambda d: self.set(**d))
