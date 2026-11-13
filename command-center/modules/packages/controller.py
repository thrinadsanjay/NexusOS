"""Software Center: APT/dpkg through nexus_core.packages (queries) and the agent (changes)."""

from __future__ import annotations

import json

from nexus_center.base import ModuleController
from nexus_core import activity, agent_client, notifications, packages
from PySide6.QtCore import Slot


class Controller(ModuleController):
    def __init__(self, tasks, app=None) -> None:
        super().__init__(tasks, app)
        self._session: agent_client.AgentSession | None = None
        self.set(
            results=[],
            details=None,
            rdeps=[],
            installed=[],
            updates=None,
            history=[],
            repos=[],
            sections=[],
            plan=None,
            op={"running": False, "percent": 0, "phase": "", "log": ""},
            agent=agent_client.available(),
        )

    @Slot()
    def refresh(self) -> None:
        self.run(packages.lock_status, lambda lock: self.set(lock=lock, agent=agent_client.available()))

    # ------------------------------------------------------------ browse/search
    @Slot(str)
    def search(self, term: str) -> None:
        self.run(lambda: packages.search(term, limit=150), lambda r: self.set(results=r))

    @Slot(str)
    def browse(self, section: str) -> None:
        self.run(lambda: packages.search("", limit=300, section=section), lambda r: self.set(results=r))

    @Slot()
    def loadSections(self) -> None:
        self.run(packages.sections, lambda s: self.set(sections=[{"name": n, "count": c} for n, c in s]))

    @Slot(str)
    def select(self, name: str) -> None:
        def load() -> dict:
            return {"details": packages.details(name), "rdeps": packages.reverse_dependencies(name)}

        self.run(load, lambda d: self.set(**d))

    @Slot(bool)
    def loadInstalled(self, apps_only: bool) -> None:
        self.run(
            packages.installed_applications if apps_only else packages.installed_packages,
            lambda r: self.set(installed=r),
        )

    @Slot()
    def loadUpdates(self) -> None:
        self.run(lambda: packages.plan("upgrade"), lambda p: self.set(updates=p))

    @Slot()
    def loadHistory(self) -> None:
        self.run(lambda: packages.history(200), lambda h: self.set(history=h))

    @Slot()
    def loadRepos(self) -> None:
        self.run(packages.repositories, lambda r: self.set(repos=r))

    # ------------------------------------------------------------ operations
    @Slot(str, str)
    def plan(self, operation: str, names_json: str) -> None:
        """Simulate first; the page shows the exact changes and command before anything runs."""
        names = json.loads(names_json or "[]")
        self.run(lambda: packages.plan(operation, names), lambda p: self.set(plan=p))

    @Slot()
    def execute(self) -> None:
        plan = self._data.get("plan")
        if not plan:
            return
        op, names = plan["operation"], plan["requested"]
        expected = [f"{c['action']}:{c['name']}" for c in plan["changes"]]
        self.set(op={"running": True, "percent": 0, "phase": "starting", "log": ""}, plan=None)
        lines: list[str] = []

        def work(emit, cancel) -> dict:
            session = agent_client.AgentSession(
                f"apt.{op}", {"packages": names, "expected": expected} if op != "update" else {"packages": []}
            )
            self._session = session
            for event in session.events():
                if event.get("type") == "result":
                    return event.get("data") or {}
                emit(event)
            return {}

        def progress(event: dict) -> None:
            if event.get("type") == "log":
                lines.append(event["line"])
                del lines[:-300]  # bounded log in memory
            current = dict(self._data["op"])
            if event.get("type") == "progress":
                current.update(
                    percent=event.get("percent", 0), phase=event.get("phase", ""), message=event.get("message", "")
                )
            current["log"] = "\n".join(lines)
            self.set(op=current)

        def done(result: dict) -> None:
            self._session = None
            cancelled = result.get("cancelled")
            self.set(
                op={
                    **self._data["op"],
                    "running": False,
                    "percent": 100 if not cancelled else self._data["op"]["percent"],
                    "phase": "cancelled" if cancelled else "done",
                }
            )
            activity.record(f"packages.{op}", " ".join(names) or op, "cancelled" if cancelled else "ok")
            notifications.notify(
                f"Package {op} {'cancelled' if cancelled else 'completed'}",
                " ".join(names)[:200],
                severity="info" if cancelled else "success",
                category="packages",
                source="software-center",
            )
            self.toast.emit("success", f"{op} finished")
            self.refresh()

        def failed(message: str, hint: str) -> None:
            self._session = None
            self.set(op={**self._data["op"], "running": False, "phase": "failed"})
            activity.record(f"packages.{op}", " ".join(names) or op, "failed", message)
            notifications.notify(
                f"Package {op} failed",
                message,
                severity="error",
                category="packages",
                source="software-center",
                dedupe_key=f"apt-fail:{op}",
            )

        self.run(work, done, progress=progress, on_error=failed)

    @Slot()
    def cancel(self) -> None:
        if self._session is not None:
            self._session.cancel()

    @Slot()
    def dismissPlan(self) -> None:
        self.set(plan=None)

    @Slot(str, str, str, str, str)
    def addRepository(self, name: str, uri: str, suites: str, components: str, signed_by: str) -> None:
        params = {
            "name": name,
            "uri": uri,
            "suites": suites.split(),
            "components": components.split(),
            "signed_by": signed_by,
        }
        self.run(
            lambda: agent_client.call("apt.repo.add", params),
            lambda r: (self.toast.emit("success", f"repository added: {r.get('file')}"), self.loadRepos()),
            record=("packages.repo.add", name),
        )

    @Slot(str)
    def removeRepository(self, name: str) -> None:
        self.run(
            lambda: agent_client.call("apt.repo.remove", {"name": name}),
            lambda r: (self.toast.emit("success", "repository removed"), self.loadRepos()),
            record=("packages.repo.remove", name),
        )
