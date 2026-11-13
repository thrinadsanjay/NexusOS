"""Unified notification centre with de-duplication and rate limiting.

Repeated events with the same ``dedupe_key`` increment a counter on the existing
undismissed notification instead of creating new rows, so the user is not flooded.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from nexus_core.store import Store, default_store, now

Severity = Literal["info", "success", "warning", "error"]
CATEGORIES = (
    "updates",
    "packages",
    "containers",
    "applications",
    "gateway",
    "certificates",
    "storage",
    "network",
    "backup",
    "ai",
    "operations",
    "security",
)
DEFAULT_PREFS = {c: True for c in CATEGORIES}


class Notification(BaseModel):
    id: int
    ts: float
    severity: str
    category: str
    title: str
    body: str
    source: str
    action: str | None = None
    count: int = 1
    dismissed: bool = False


def preferences(store: Store | None = None) -> dict[str, bool]:
    store = store or default_store()
    return {**DEFAULT_PREFS, **(store.get_setting("notifications.preferences", {}) or {})}


def set_preference(category: str, enabled: bool, store: Store | None = None) -> None:
    store = store or default_store()
    prefs = preferences(store)
    if category not in prefs:
        raise ValueError(f"unknown notification category {category!r}")
    prefs[category] = enabled
    store.set_setting("notifications.preferences", prefs)


def notify(
    title: str,
    body: str = "",
    *,
    severity: Severity = "info",
    category: str = "operations",
    source: str = "nexusos",
    action: str | None = None,
    dedupe_key: str | None = None,
    store: Store | None = None,
) -> int | None:
    """Create (or bump) a notification. Returns its id, or None if the category is muted."""
    store = store or default_store()
    if category not in CATEGORIES:
        raise ValueError(f"unknown notification category {category!r}")
    if not preferences(store).get(category, True):
        return None
    if dedupe_key:
        rows = store.query(
            "SELECT id FROM notifications WHERE dedupe_key=? AND dismissed=0 ORDER BY id DESC LIMIT 1", (dedupe_key,)
        )
        if rows:
            store.execute(
                "UPDATE notifications SET count=count+1, ts=?, body=? WHERE id=?", (now(), body[:2000], rows[0]["id"])
            )
            return int(rows[0]["id"])
    nid = store.execute(
        "INSERT INTO notifications(ts, severity, category, title, body, source, action, dedupe_key) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (now(), severity, category, title[:200], body[:2000], source, action, dedupe_key),
    )
    store.trim("notifications")
    return nid


def list_notifications(include_dismissed: bool = False, store: Store | None = None) -> list[Notification]:
    store = store or default_store()
    rows = store.query(
        "SELECT * FROM notifications WHERE dismissed IN (0, ?) ORDER BY ts DESC LIMIT 500",
        (1 if include_dismissed else 0,),
    )
    return [Notification(**{**dict(r), "dismissed": bool(r["dismissed"])}) for r in rows]


def dismiss(notification_id: int | None = None, store: Store | None = None) -> None:
    """Dismiss one notification, or all when ``notification_id`` is None."""
    store = store or default_store()
    if notification_id is None:
        store.execute("UPDATE notifications SET dismissed=1")
    else:
        store.execute("UPDATE notifications SET dismissed=1 WHERE id=?", (notification_id,))


def unread_count(store: Store | None = None) -> int:
    store = store or default_store()
    return int(store.query("SELECT COUNT(*) AS n FROM notifications WHERE dismissed=0")[0]["n"])
