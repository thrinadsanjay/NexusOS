"""Lightweight local metadata store (SQLite, per user).

Holds Command Center settings, SSH connection profiles (never secrets), connection
history, notifications, activity history and chat conversations. One file, WAL mode,
mode 0600, with hard row limits so history never grows without bound.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from nexus_core import paths

SCHEMA_VERSION = 1
LIMITS = {"activity": 5000, "notifications": 1000, "ssh_history": 500, "chat_messages": 20000}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ssh_profiles (
    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, data TEXT NOT NULL,
    favorite INTEGER NOT NULL DEFAULT 0, grp TEXT NOT NULL DEFAULT 'Custom',
    created REAL NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS ssh_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id TEXT NOT NULL, ts REAL NOT NULL, event TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, severity TEXT NOT NULL, category TEXT NOT NULL,
    title TEXT NOT NULL, body TEXT NOT NULL, source TEXT NOT NULL, action TEXT, dedupe_key TEXT,
    count INTEGER NOT NULL DEFAULT 1, dismissed INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS notifications_dedupe ON notifications(dedupe_key, dismissed);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
    target TEXT NOT NULL, outcome TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS chat_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, model TEXT NOT NULL,
    system_prompt TEXT NOT NULL DEFAULT '', created REAL NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id)
    ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, ts REAL NOT NULL);
"""


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.data_dir() / "command-center.db"
        self._lock = threading.RLock()
        new = not self.path.exists()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        if new:
            os.chmod(self.path, 0o600)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),)
        )

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def execute(self, sql: str, params: tuple = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return cur.lastrowid or cur.rowcount

    def trim(self, table: str) -> None:
        """Keep only the newest LIMITS[table] rows."""
        limit = LIMITS[table]
        self.execute(f"DELETE FROM {table} WHERE id NOT IN (SELECT id FROM {table} ORDER BY id DESC LIMIT ?)", (limit,))  # noqa: S608 - table from fixed LIMITS keys

    # ----------------------------------------------------------- settings
    def get_setting(self, key: str, default: Any = None) -> Any:
        rows = self.query("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def set_setting(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_default: Store | None = None
_default_lock = threading.Lock()


def default_store() -> Store:
    """Process-wide store, opened on first use (lazy: nothing touches disk at import)."""
    global _default
    with _default_lock:
        if _default is None:
            _default = Store()
        return _default


def now() -> float:
    return time.time()
