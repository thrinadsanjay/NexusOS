"""Activity history (user-level audit trail of operations started from CLI/Command Center).

Privileged operations are additionally audited by the agent in /var/log/nexusos/agent-audit.log.
"""

from __future__ import annotations

import getpass

from pydantic import BaseModel

from nexus_core.redact import redact_text
from nexus_core.store import Store, default_store, now


class ActivityEntry(BaseModel):
    id: int
    ts: float
    actor: str
    action: str
    target: str
    outcome: str
    detail: str


def record(action: str, target: str, outcome: str, detail: str = "", store: Store | None = None) -> None:
    store = store or default_store()
    store.execute(
        "INSERT INTO activity(ts, actor, action, target, outcome, detail) VALUES (?,?,?,?,?,?)",
        (now(), getpass.getuser(), action, target, outcome, redact_text(detail)[:2000]),
    )
    store.trim("activity")


def recent(limit: int = 200, query: str = "", store: Store | None = None) -> list[ActivityEntry]:
    store = store or default_store()
    like = f"%{query}%"
    rows = store.query(
        "SELECT * FROM activity WHERE action LIKE ? OR target LIKE ? OR outcome LIKE ? ORDER BY id DESC LIMIT ?",
        (like, like, like, min(limit, 1000)),
    )
    return [ActivityEntry(**dict(r)) for r in rows]
