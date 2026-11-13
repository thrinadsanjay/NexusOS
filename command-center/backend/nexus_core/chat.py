"""Native chat conversations stored locally (SQLite). Inference goes to Ollama directly."""

from __future__ import annotations

from pydantic import BaseModel

from nexus_core.store import Store, default_store, now

MAX_CONTEXT_MESSAGES = 40


class Message(BaseModel):
    role: str
    content: str
    ts: float


class Conversation(BaseModel):
    id: int
    title: str
    model: str
    system_prompt: str
    updated: float


def create(model: str, system_prompt: str = "", title: str = "New conversation", store: Store | None = None) -> int:
    store = store or default_store()
    ts = now()
    return store.execute(
        "INSERT INTO chat_conversations(title, model, system_prompt, created, updated) VALUES (?,?,?,?,?)",
        (title[:120], model, system_prompt[:4000], ts, ts),
    )


def conversations(store: Store | None = None) -> list[Conversation]:
    store = store or default_store()
    return [
        Conversation(**dict(r))
        for r in store.query(
            "SELECT id, title, model, system_prompt, updated FROM chat_conversations ORDER BY updated DESC LIMIT 200"
        )
    ]


def messages(conversation_id: int, store: Store | None = None) -> list[Message]:
    store = store or default_store()
    return [
        Message(**dict(r))
        for r in store.query(
            "SELECT role, content, ts FROM chat_messages WHERE conversation_id=? ORDER BY id", (conversation_id,)
        )
    ]


def add_message(conversation_id: int, role: str, content: str, store: Store | None = None) -> None:
    store = store or default_store()
    ts = now()
    store.execute(
        "INSERT INTO chat_messages(conversation_id, role, content, ts) VALUES (?,?,?,?)",
        (conversation_id, role, content, ts),
    )
    store.execute("UPDATE chat_conversations SET updated=? WHERE id=?", (ts, conversation_id))
    if role == "user":
        rows = store.query("SELECT COUNT(*) AS n FROM chat_messages WHERE conversation_id=?", (conversation_id,))
        if rows[0]["n"] == 1:
            store.execute(
                "UPDATE chat_conversations SET title=? WHERE id=?", (content.strip()[:60] or "Chat", conversation_id)
            )
    store.trim("chat_messages")


def context(conversation_id: int, store: Store | None = None) -> list[dict[str, str]]:
    """Messages to send to the model: system prompt + the most recent turns (bounded)."""
    store = store or default_store()
    conv = store.query("SELECT system_prompt FROM chat_conversations WHERE id=?", (conversation_id,))
    out = []
    if conv and conv[0]["system_prompt"]:
        out.append({"role": "system", "content": conv[0]["system_prompt"]})
    out += [{"role": m.role, "content": m.content} for m in messages(conversation_id, store)[-MAX_CONTEXT_MESSAGES:]]
    return out


def clear(conversation_id: int, store: Store | None = None) -> None:
    store = store or default_store()
    store.execute("DELETE FROM chat_messages WHERE conversation_id=?", (conversation_id,))


def delete(conversation_id: int, store: Store | None = None) -> None:
    store = store or default_store()
    store.execute("DELETE FROM chat_conversations WHERE id=?", (conversation_id,))
