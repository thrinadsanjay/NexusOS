"""Gateway: native NGINX routes and certificates. Reads unprivileged; writes use the user's sudo rights."""

from __future__ import annotations

import json

from nexus_center.base import ModuleController
from nexus_core import agent_client, notifications, paths
from nexus_core.gateway import certs, status
from nexus_core.gateway.model import Route
from PySide6.QtCore import Slot

OP_LABELS = {
    "gateway.route.save": "Save gateway route",
    "gateway.route.delete": "Delete gateway route",
    "gateway.apply": "Apply gateway configuration",
    "gateway.rollback": "Roll back gateway configuration",
    "gateway.nginx.test": "Test NGINX configuration",
    "gateway.nginx.reload": "Reload NGINX",
    "gateway.cert.issue": "Issue a certificate",
    "gateway.cert.import": "Import a certificate",
    "gateway.cert.renew": "Renew certificates",
}


class Controller(ModuleController):
    def __init__(self, tasks, app=None) -> None:
        super().__init__(tasks, app)
        self.set(status=None, routes=[], certs=[], checks={}, output="", logs="", agent=agent_client.available())

    @Slot()
    def refresh(self) -> None:
        def load() -> dict:
            st = status.status()
            certificates = certs.inventory(paths.gateway_dir())
            for c in certificates:
                if c.status != "ok":
                    notifications.notify(
                        f"Certificate {c.name} {c.status}",
                        f"expires in {c.days_left} days",
                        severity="warning" if c.status == "warning" else "error",
                        category="certificates",
                        source="gateway",
                        dedupe_key=f"cert:{c.name}",
                    )
            return {"status": st, "routes": status.routes(), "certs": certificates, "agent": agent_client.available()}

        self.run(load, lambda d: self.set(**d))

    def _agent(self, op: str, params: dict, label: str, after=None) -> None:
        def done(result: dict) -> None:
            self.set(output=json.dumps(result, indent=2))
            if result.get("ok") is False:
                self.toast.emit("error", result.get("message", f"{label} failed"))
                notifications.notify(
                    f"Gateway: {label} failed",
                    result.get("message", ""),
                    severity="error",
                    category="gateway",
                    source="gateway",
                    dedupe_key=f"gw:{label}",
                )
            else:
                self.toast.emit("success", f"{label}: done")
            self.refresh()
            if after:
                after()

        self.run(
            lambda: agent_client.call(op, params, label=OP_LABELS.get(op, op)),
            done,
            record=(f"gateway.{label}", json.dumps(params)[:200]),
            notify_category="gateway",
            label=label,
        )

    @Slot(str)
    def saveRoute(self, route_json: str) -> None:
        route = Route(**json.loads(route_json))  # validate in-process first for immediate feedback
        self._agent("gateway.route.save", {"route": route.model_dump()}, f"save route {route.id}")

    @Slot(str)
    def approve(self, route_id: str) -> None:
        route = next(r for r in self._data["routes"] if r["id"] == route_id)
        self._agent("gateway.route.save", {"route": {**route, "approved": True}}, f"approve {route_id}")

    @Slot(str)
    def deleteRoute(self, route_id: str) -> None:
        self._agent("gateway.route.delete", {"id": route_id}, f"delete {route_id}")

    @Slot()
    def apply(self) -> None:
        self._agent("gateway.apply", {}, "apply")

    @Slot()
    def rollback(self) -> None:
        self._agent("gateway.rollback", {}, "rollback")

    @Slot()
    def testNginx(self) -> None:
        self._agent("gateway.nginx.test", {}, "nginx -t")

    @Slot()
    def reloadNginx(self) -> None:
        self._agent("gateway.nginx.reload", {}, "reload")

    @Slot(str)
    def testBackend(self, route_id: str) -> None:
        route = Route(**next(r for r in self._data["routes"] if r["id"] == route_id))
        self.run(
            lambda: status.test_backend(route),
            lambda check: self.set(checks={**self._data.get("checks", {}), route_id: check}),
        )

    @Slot(str, str, str, str)
    def issueCertificate(self, mode: str, name: str, hostnames: str, email: str) -> None:
        params = {"mode": mode, "name": name, "hostnames": hostnames.split(), "email": email or None}
        self._agent("gateway.cert.issue", params, f"issue {mode} certificate")

    @Slot(str, str, str)
    def importCertificate(self, name: str, cert_file: str, key_file: str) -> None:
        self._agent(
            "gateway.cert.import",
            {"name": name, "cert_file": cert_file.replace("file://", ""), "key_file": key_file.replace("file://", "")},
            "import certificate",
        )

    @Slot()
    def renew(self) -> None:
        self._agent("gateway.cert.renew", {}, "renew certificates")

    @Slot(str)
    def loadLogs(self, kind: str) -> None:
        self.run(
            lambda: agent_client.call("gateway.logs", {"kind": kind, "lines": 300}, label="Read gateway logs"),
            lambda r: self.set(logs="\n".join(r.get("lines", []))),
        )
