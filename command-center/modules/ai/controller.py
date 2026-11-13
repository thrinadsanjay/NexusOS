"""Local AI: Ollama status, models and the native streaming chat. Loads nothing large by itself."""

from __future__ import annotations

import threading

from nexus_center.base import ModuleController
from nexus_core import chat, notifications, ollama, services
from nexus_core.store import default_store
from PySide6.QtCore import Slot


class Controller(ModuleController):
    def __init__(self, tasks, app=None) -> None:
        super().__init__(tasks, app)
        self._stop = threading.Event()
        self.set(
            status=None,
            models=[],
            running=[],
            gpu=None,
            pull=None,
            conversations=[],
            conversation=None,
            messages=[],
            streaming=False,
            draft="",
            info={},
            installDoc=ollama.INSTALL_DOC,
            systemPrompt=default_store().get_setting("ai.system_prompt", ""),
            options=default_store().get_setting("ai.options", {}),
        )

    @Slot()
    def refresh(self) -> None:
        def load() -> dict:
            st = ollama.ollama_status()
            out = {
                "status": st,
                "conversations": chat.conversations(),
                "gpu": ollama.gpu_inference_support(),
                "serviceState": services.is_active("ollama.service"),
            }
            if st.reachable:
                out["models"] = ollama.list_models()
                out["running"] = [{**r.model_dump(), "mode": r.mode} for r in ollama.running()]
            return out

        self.run(load, lambda d: self.set(**d))

    @Slot(str)
    def service(self, action: str) -> None:
        self.run(
            lambda: services.control("ollama.service", action),
            lambda _: self.refresh(),
            record=(f"ai.service.{action}", "ollama.service"),
        )

    @Slot(str)
    def showModel(self, name: str) -> None:
        self.run(lambda: ollama.show(name), lambda info: self.set(info={**self._data.get("info", {}), name: info}))

    @Slot(str)
    def pull(self, name: str) -> None:
        self._stop.clear()

        def work(emit, cancel):
            for event in ollama.pull(name, cancel=self._stop):
                emit(event)

        def progress(e: dict) -> None:
            total, done = e.get("total") or 0, e.get("completed") or 0
            self.set(pull={"name": name, "status": e.get("status", ""), "fraction": done / total if total else 0})

        def done(_):
            self.set(pull=None)
            notifications.notify(f"Model {name} downloaded", severity="success", category="ai", source="local-ai")
            self.refresh()

        self.set(pull={"name": name, "status": "starting", "fraction": 0})
        self.run(
            work,
            done,
            progress=progress,
            record=("ai.pull", name),
            notify_category="ai",
            label=f"pull {name}",
            on_error=lambda m, h: self.set(pull=None),
        )

    @Slot()
    def cancelPull(self) -> None:
        self._stop.set()

    @Slot(str)
    def deleteModel(self, name: str) -> None:
        self.run(lambda: ollama.delete(name), lambda _: self.refresh(), record=("ai.delete", name))

    # ------------------------------------------------------------ chat
    @Slot(str)
    def newConversation(self, model: str) -> None:
        cid = chat.create(model, self._data.get("systemPrompt", ""))
        self.set(conversations=chat.conversations())
        self.openConversation(cid)

    @Slot(int)
    def openConversation(self, cid: int) -> None:
        conv = next((c for c in chat.conversations() if c.id == cid), None)
        self.set(conversation=conv, messages=chat.messages(cid), draft="")

    @Slot(int)
    def deleteConversation(self, cid: int) -> None:
        chat.delete(cid)
        self.set(conversation=None, messages=[], conversations=chat.conversations())

    @Slot()
    def clearConversation(self) -> None:
        conv = self._data.get("conversation")
        if conv:
            chat.clear(conv["id"])
            self.set(messages=[])

    @Slot(str)
    def setSystemPrompt(self, prompt: str) -> None:
        default_store().set_setting("ai.system_prompt", prompt[:4000])
        self.set(systemPrompt=prompt)

    @Slot(float, int)
    def setOptions(self, temperature: float, num_ctx: int) -> None:
        opts = {"temperature": temperature, "num_ctx": num_ctx or None}
        default_store().set_setting("ai.options", opts)
        self.set(options=opts)

    @Slot(str)
    def send(self, text: str) -> None:
        conv = self._data.get("conversation")
        if not conv or not text.strip() or self._data.get("streaming"):
            return
        cid, model = conv["id"], conv["model"]
        chat.add_message(cid, "user", text)
        self._stop.clear()
        self.set(messages=chat.messages(cid), streaming=True, draft="")
        parts: list[str] = []
        opts = ollama.ChatOptions(**{k: v for k, v in (self._data.get("options") or {}).items() if v is not None})

        def work(emit, cancel):
            for chunk in ollama.chat_stream(model, chat.context(cid), opts, cancel=self._stop):
                emit(chunk)

        def progress(chunk: str) -> None:
            parts.append(chunk)
            self.set(draft="".join(parts))

        def finish(_=None) -> None:
            reply = "".join(parts)
            if reply:
                chat.add_message(cid, "assistant", reply + ("\n\n*(stopped)*" if self._stop.is_set() else ""))
            self.set(messages=chat.messages(cid), streaming=False, draft="", conversations=chat.conversations())

        self.run(work, finish, progress=progress, on_error=lambda m, h: finish())

    @Slot()
    def stop(self) -> None:
        self._stop.set()
