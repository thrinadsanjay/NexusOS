"""Files: in-app browsing; operations through KIO; full file management in Dolphin."""

from __future__ import annotations

import os

from nexus_center.base import ModuleController
from nexus_core import files
from PySide6.QtCore import Slot


class Controller(ModuleController):
    def __init__(self, tasks, app=None) -> None:
        super().__init__(tasks, app)
        self.set(path=os.path.expanduser("~"), entries=[], places=[], hidden=False, results=[])

    @Slot()
    def refresh(self) -> None:
        self.open(self._data["path"])
        self.run(files.places, lambda p: self.set(places=p))

    @Slot(str)
    def open(self, path: str) -> None:
        hidden = self._data.get("hidden", False)
        self.run(lambda: files.list_dir(path, hidden), lambda e: self.set(entries=e, path=os.path.expanduser(path)))

    @Slot(bool)
    def setHidden(self, hidden: bool) -> None:
        self.set(hidden=hidden)
        self.open(self._data["path"])

    @Slot(str)
    def openInDolphin(self, path: str) -> None:
        self.run(lambda: files.open_in_dolphin(path), lambda _: None)

    @Slot(str)
    def openFile(self, path: str) -> None:
        self.run(lambda: files.open_file(path), lambda _: None)

    @Slot(str, str)
    def rename(self, path: str, new_name: str) -> None:
        self.run(
            lambda: files.rename(path, new_name), lambda _: self.open(self._data["path"]), record=("files.rename", path)
        )

    @Slot(str)
    def trash(self, path: str) -> None:
        self.run(lambda: files.trash([path]), lambda _: self.open(self._data["path"]), record=("files.trash", path))

    @Slot(str, str, bool)
    def transfer(self, path: str, destination: str, move: bool) -> None:
        self.run(
            lambda: (files.move if move else files.copy)([path], destination),
            lambda _: self.open(self._data["path"]),
            record=("files.move" if move else "files.copy", path),
        )

    @Slot(str)
    def search(self, query: str) -> None:
        self.run(lambda: files.search(query), lambda r: self.set(results=r))

    @Slot(str)
    def extract(self, path: str) -> None:
        self.run(lambda: files.extract(path, os.path.dirname(path)), lambda _: None)

    @Slot(str)
    def compress(self, path: str) -> None:
        self.run(lambda: files.compress([path], path.rstrip("/") + ".tar.gz"), lambda _: None)
