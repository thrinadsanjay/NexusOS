"""Storage: inventory, usage, SMART, mount/unmount; guarded formatting via UDisks2."""

from __future__ import annotations

from nexus_center.base import ModuleController
from nexus_core import notifications, storage
from PySide6.QtCore import Slot


class Controller(ModuleController):
    def __init__(self, tasks, app=None) -> None:
        super().__init__(tasks, app)
        self.set(disks=[], usage=[], swaps=[], smart={}, temps={}, plan=None)

    @Slot()
    def refresh(self) -> None:
        def load() -> dict:
            disks = storage.devices()
            flat = []
            for disk in disks:
                flat.append(
                    {**disk.model_dump(exclude={"children"}), "media": disk.media, "depth": 0, "disk": disk.path}
                )
                for child in disk.children:
                    flat.append({**child.model_dump(exclude={"children"}), "media": "", "depth": 1, "disk": disk.path})
            return {
                "disks": flat,
                "usage": storage.usage(),
                "swaps": storage.swaps(),
                "temps": storage.disk_temperatures(),
            }

        self.run(load, lambda d: self.set(**d))

    @Slot(str)
    def readSmart(self, device: str) -> None:
        def done(summary) -> None:
            self.set(smart={**self._data.get("smart", {}), device: summary})
            if summary.available and summary.passed is False:
                notifications.notify(
                    f"Disk {device} reports SMART failure",
                    "Back up its data now.",
                    severity="error",
                    category="storage",
                    source="storage",
                    dedupe_key=f"smart:{device}",
                )

        self.run(lambda: storage.smart(device), done)

    @Slot(str)
    def mount(self, device: str) -> None:
        self.run(
            lambda: storage.mount(device),
            lambda msg: (self.toast.emit("success", msg), self.refresh()),
            record=("storage.mount", device),
        )

    @Slot(str)
    def unmount(self, device: str) -> None:
        self.run(lambda: storage.unmount(device), lambda _: self.refresh(), record=("storage.unmount", device))

    @Slot(str, str, str)
    def planFormat(self, device: str, filesystem: str, label: str) -> None:
        self.run(lambda: storage.plan_format(device, filesystem, label), lambda p: self.set(plan=p))

    @Slot(str)
    def executeFormat(self, typed: str) -> None:
        plan = storage.DestructivePlan(**self._data["plan"])
        self.set(plan=None)
        self.run(
            lambda: storage.execute_format(plan, typed),
            lambda _: (self.toast.emit("success", "formatted"), self.refresh()),
            record=("storage.format", f"{plan.device} {plan.filesystem}"),
            notify_category="storage",
            label=f"format {plan.device}",
        )

    @Slot()
    def dismissPlan(self) -> None:
        self.set(plan=None)
