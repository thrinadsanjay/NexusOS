"""Files: Explorer-style browsing; operations through KIO; full file management in Dolphin."""

from __future__ import annotations

import os

from nexus_center.base import ModuleController
from nexus_core import files, storage
from PySide6.QtCore import Slot


class Controller(ModuleController):
    def __init__(self, tasks, app=None) -> None:
        super().__init__(tasks, app)
        self.set(
            path=os.path.expanduser("~"),
            entries=[],
            places=[],
            quick=[],
            drives=[],
            hidden=False,
            results=[],
            clipboard={"paths": [], "cut": False},
        )

    @Slot()
    def refresh(self) -> None:
        self.open(self._data["path"])
        self.run(
            lambda: {"places": files.places(), "quick": files.quick_access(), "drives": storage.usage()},
            lambda d: self.set(**d),
        )

    @Slot(str)
    def open(self, path: str) -> None:
        hidden = self._data.get("hidden", False)
        target = os.path.expanduser(path or "~")
        self.run(lambda: files.list_dir(target, hidden), lambda e: self.set(entries=e, path=target, results=[]))

    @Slot()
    def reload(self) -> None:
        self.open(self._data["path"])

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
        self.run(lambda: files.rename(path, new_name), lambda _: self.reload(), record=("files.rename", path))

    @Slot()
    def newFolder(self) -> None:
        parent = self._data["path"]
        self.run(
            lambda: files.make_folder(parent, files.unique_name(parent, "New folder")),
            lambda created: (self.set(created=created), self.reload()),
            record=("files.mkdir", parent),
        )

    @Slot("QVariantList")
    def trash(self, paths: list) -> None:
        items = [str(p) for p in paths]
        self.run(lambda: files.trash(items), lambda _: self.reload(), record=("files.trash", ", ".join(items)[:200]))

    @Slot("QVariantList", bool)
    def setClipboard(self, paths: list, cut: bool) -> None:
        self.set(clipboard={"paths": [str(p) for p in paths], "cut": cut})

    @Slot()
    def paste(self) -> None:
        clip = self._data.get("clipboard") or {}
        items, cut, dest = list(clip.get("paths") or []), bool(clip.get("cut")), self._data["path"]
        if not items:
            return

        def done(_: object) -> None:
            if cut:
                self.set(clipboard={"paths": [], "cut": False})
            self.reload()

        self.run(
            lambda: (files.move if cut else files.copy)(items, dest),
            done,
            record=("files.move" if cut else "files.copy", ", ".join(items)[:200]),
        )

    @Slot("QVariantList", str, bool)
    def transfer(self, paths: list, destination: str, move: bool) -> None:
        items = [str(p) for p in paths]
        self.run(
            lambda: (files.move if move else files.copy)(items, destination),
            lambda _: self.reload(),
            record=("files.move" if move else "files.copy", ", ".join(items)[:200]),
        )

    @Slot(str)
    def search(self, query: str) -> None:
        self.run(lambda: files.search(query), lambda r: self.set(results=r))

    @Slot(str)
    def extract(self, path: str) -> None:
        self.run(lambda: files.extract(path, os.path.dirname(path)), lambda _: None)

    @Slot("QVariantList")
    def compress(self, paths: list) -> None:
        items = [str(p) for p in paths]
        if items:
            archive = (
                items[0].rstrip("/") if len(items) == 1 else os.path.join(self._data["path"], "Archive")
            ) + ".tar.gz"
            self.run(lambda: files.compress(items, archive), lambda _: None)
