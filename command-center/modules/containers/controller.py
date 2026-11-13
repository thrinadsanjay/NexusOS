"""Containers: Docker Engine (local socket) and Compose. Stats are fetched on demand only."""

from __future__ import annotations

import json
from pathlib import Path

from nexus_center.base import ModuleController
from nexus_core import compose, terminal
from nexus_core import docker as engine
from PySide6.QtCore import Slot


class Controller(ModuleController):
    poll_interval_ms = 10_000  # container list only, while visible

    def __init__(self, tasks, app=None) -> None:
        super().__init__(tasks, app)
        self.set(
            available=None,
            containers=[],
            images=[],
            volumes=[],
            networks=[],
            projects=[],
            logs="",
            inspect="",
            stats=None,
            note=engine.DOCKER_SECURITY_NOTE,
            pull=None,
            composeCheck="",
        )

    def _client(self) -> engine.DockerClient:
        return engine.DockerClient()

    @Slot()
    def refresh(self) -> None:
        def load() -> dict:
            status = engine.docker_status(include_containers=False)
            if not status.reachable:
                return {"available": False, "status": status}
            with self._client() as c:
                return {
                    "available": True,
                    "status": status,
                    "containers": c.containers(),
                    "projects": c.compose_projects(),
                }

        self.run(load, lambda d: self.set(**d))

    @Slot(str)
    def loadTab(self, tab: str) -> None:
        def load() -> dict:
            with self._client() as c:
                if tab == "images":
                    return {"images": c.images()}
                if tab == "volumes":
                    return {"volumes": c.volumes()}
                if tab == "networks":
                    return {"networks": c.networks()}
                return {"diskUsage": c.disk_usage()}

        self.run(load, lambda d: self.set(**d))

    @Slot(str, str)
    def containerAction(self, ident: str, action: str) -> None:
        def act() -> None:
            with self._client() as c:
                if action == "remove":
                    c.remove_container(ident, force=True)
                else:
                    c.container_action(ident, action)

        self.run(
            act,
            lambda _: self.refresh(),
            record=(f"container.{action}", ident),
            notify_category="containers",
            label=f"{action} {ident}",
        )

    @Slot(str)
    def logs(self, ident: str) -> None:
        self.run(lambda: self._client().logs(ident, 500), lambda t: self.set(logs=t))

    @Slot(str)
    def inspect(self, ident: str) -> None:
        self.run(lambda: json.dumps(self._client().inspect_container(ident), indent=2), lambda t: self.set(inspect=t))

    @Slot(str)
    def stats(self, ident: str) -> None:
        self.run(lambda: {"id": ident, **self._client().stats(ident)}, lambda s: self.set(stats=s))

    @Slot(str)
    def openShell(self, ident: str) -> None:
        tab = terminal.TerminalTab(
            title=f"docker {ident}",
            command=["docker", "exec", "-it", ident, "sh", "-c", "command -v bash >/dev/null && exec bash || exec sh"],
        )
        self.run(lambda: terminal.open_terminal(tab), lambda _: None, record=("container.shell", ident))

    @Slot(str)
    def pullImage(self, ref: str) -> None:
        def work(emit, cancel):
            with self._client() as c:
                for event in c.pull(ref):
                    if cancel.is_set():
                        break
                    emit(event)

        self.set(pull={"ref": ref, "status": "starting"})
        self.run(
            work,
            lambda _: (self.set(pull=None), self.loadTab("images")),
            progress=lambda e: self.set(
                pull={"ref": ref, "status": e.get("status", ""), "progress": e.get("progress", "")}
            ),
            record=("image.pull", ref),
        )

    @Slot(str, bool)
    def removeImage(self, ident: str, force: bool) -> None:
        self.run(
            lambda: self._client().remove_image(ident, force),
            lambda _: self.loadTab("images"),
            record=("image.remove", ident),
        )

    @Slot(str, str, str)
    def tagImage(self, ident: str, repo: str, tag: str) -> None:
        self.run(lambda: self._client().tag_image(ident, repo, tag), lambda _: self.loadTab("images"))

    @Slot(str)
    def searchImages(self, term: str) -> None:
        self.run(lambda: self._client().search(term), lambda r: self.set(searchResults=r))

    @Slot(str)
    def createVolume(self, name: str) -> None:
        self.run(lambda: self._client().create_volume(name), lambda _: self.loadTab("volumes"))

    @Slot(str)
    def removeVolume(self, name: str) -> None:
        self.run(
            lambda: self._client().remove_volume(name),
            lambda _: self.loadTab("volumes"),
            record=("volume.remove", name),
        )

    @Slot()
    def pruneVolumes(self) -> None:
        self.run(
            lambda: self._client().prune_volumes(), lambda _: self.loadTab("volumes"), record=("volume.prune", "*")
        )

    @Slot(str)
    def createNetwork(self, name: str) -> None:
        self.run(lambda: self._client().create_network(name), lambda _: self.loadTab("networks"))

    @Slot(str)
    def removeNetwork(self, name: str) -> None:
        self.run(lambda: self._client().remove_network(name), lambda _: self.loadTab("networks"))

    @Slot(str, str, bool)
    def networkConnect(self, network: str, container: str, connect: bool) -> None:
        self.run(
            lambda: (self._client().connect if connect else self._client().disconnect)(network, container),
            lambda _: self.loadTab("networks"),
        )

    @Slot()
    def pruneNetworks(self) -> None:
        self.run(lambda: self._client().prune_networks(), lambda _: self.loadTab("networks"))

    # ------------------------------------------------------------ compose
    def _project_files(self, project: dict) -> list[Path]:
        return [Path(f) for f in (project.get("config_files") or "").split(",") if f]

    @Slot(str, str)
    def composeAction(self, name: str, action: str) -> None:
        project = next((p for p in self._data.get("projects", []) if p["name"] == name), None)
        if not project:
            return
        self.run(
            lambda: compose.run_action(name, self._project_files(project), action),
            lambda _: self.refresh(),
            record=(f"compose.{action}", name),
            notify_category="containers",
            label=f"compose {action} {name}",
        )

    @Slot(str)
    def composeLogs(self, name: str) -> None:
        project = next((p for p in self._data.get("projects", []) if p["name"] == name), None)
        if project:
            self.run(lambda: compose.logs(name, self._project_files(project)), lambda t: self.set(logs=t))

    @Slot(str, str)
    def composeValidate(self, name: str, file_url: str) -> None:
        path = Path(file_url.replace("file://", ""))
        self.run(
            lambda: compose.validate(name or path.parent.name.lower(), [path]),
            lambda r: self.set(composeCheck=("valid" if r[0] else "invalid: " + r[1])),
        )

    @Slot(str, str)
    def composeDeploy(self, name: str, file_url: str) -> None:
        path = Path(file_url.replace("file://", ""))
        self.run(
            lambda: compose.run_action(name, [path], "up"),
            lambda _: self.refresh(),
            record=("compose.deploy", f"{name} ({path})"),
            notify_category="containers",
            label=f"deploy {name}",
        )
