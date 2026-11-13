"""Network: NetworkManager devices/connections/Wi-Fi, routes, DNS, diagnostics, firewall."""

from __future__ import annotations

from nexus_center.base import ModuleController
from nexus_core import network
from PySide6.QtCore import QTimer, Slot


class Controller(ModuleController):
    def __init__(self, tasks, app=None) -> None:
        super().__init__(tasks, app)
        self.set(
            devices=[],
            connections=[],
            wifi=[],
            routes=[],
            dns={},
            connectivity="",
            diagnostics=[],
            firewall=None,
            checkpoint=None,
        )
        self._rollback_timer = QTimer(self)
        self._rollback_timer.setSingleShot(True)
        self._rollback_timer.timeout.connect(lambda: self.set(checkpoint=None))

    @Slot()
    def refresh(self) -> None:
        def load() -> dict:
            return {
                "devices": network.devices(),
                "connections": network.connections(),
                "routes": network.routes(),
                "dns": network.dns(),
                "connectivity": network.connectivity(),
            }

        self.run(load, lambda d: self.set(**d))

    @Slot(bool)
    def scanWifi(self, rescan: bool) -> None:
        self.run(lambda: network.wifi_networks(rescan), lambda w: self.set(wifi=w))

    @Slot(str, str)
    def connection(self, name: str, action: str) -> None:
        self.run(
            lambda: network.connection_action(name, action),
            lambda _: self.refresh(),
            record=(f"network.{action}", name),
            notify_category="network",
            label=f"{action} {name}",
        )

    @Slot(str)
    def diagnose(self, target: str) -> None:
        self.run(lambda: network.diagnose(target), lambda r: self.set(diagnostics=r))

    @Slot()
    def loadFirewall(self) -> None:
        self.run(network.firewall_status, lambda f: self.set(firewall=f))

    @Slot(str, str, str, str)
    def applyStatic(self, conn: str, address: str, gateway: str, dns: str) -> None:
        cfg = network.StaticIPv4(connection=conn, address=address, gateway=gateway or None, dns=dns.split())
        argv = network.static_ipv4_argv(cfg)

        def done(path: str) -> None:
            self.set(checkpoint={"path": path, "seconds": network.CHECKPOINT_TIMEOUT})
            self._rollback_timer.start(network.CHECKPOINT_TIMEOUT * 1000)
            self.refresh()

        self.run(
            lambda: network.apply_with_checkpoint(argv, conn), done, record=("network.static", f"{conn} {address}")
        )

    @Slot()
    def keepChanges(self) -> None:
        cp = self._data.get("checkpoint")
        if cp:
            self._rollback_timer.stop()
            self.run(
                lambda: network.confirm_checkpoint(cp["path"]),
                lambda _: (self.set(checkpoint=None), self.toast.emit("success", "kept")),
            )
