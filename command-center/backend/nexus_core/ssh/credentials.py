"""Secure credential storage through the freedesktop Secret Service.

On NexusOS this is KWallet (KDE Wallet implements the Secret Service API); GNOME
Keyring also works. Secrets are never written to NexusOS configuration files, the
SQLite store, logs or command lines. There is deliberately NO plaintext fallback:
if no Secret Service is available, saving a secret fails.

Only non-secret metadata (name, kind, username, rotation reminder) is kept in SQLite.
"""

from __future__ import annotations

import time
from typing import Literal, Protocol

from pydantic import BaseModel

from nexus_core.errors import DependencyMissingError, NexusError
from nexus_core.ssh.profiles import CREDENTIAL_REF_RE
from nexus_core.store import Store, default_store

APP = "nexusos"
Kind = Literal["ssh-password", "ssh-key-passphrase", "generic"]


class CredentialMeta(BaseModel):
    ref: str
    kind: Kind
    username: str = ""
    created: float
    rotate_after_days: int | None = None

    @property
    def rotation_due(self) -> bool:
        return bool(self.rotate_after_days) and time.time() > self.created + self.rotate_after_days * 86400


class SecretBackend(Protocol):
    def store(self, ref: str, kind: str, secret: str, label: str) -> None: ...
    def lookup(self, ref: str) -> str | None: ...
    def delete(self, ref: str) -> None: ...


class SecretServiceBackend:
    """Secret Service via python3-secretstorage (D-Bus). Imported lazily."""

    def _collection(self):
        try:
            import secretstorage
        except ImportError as exc:
            raise DependencyMissingError(
                "python3-secretstorage is not installed", hint="sudo apt install python3-secretstorage"
            ) from exc
        try:
            conn = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(conn)
        except Exception as exc:
            raise DependencyMissingError(
                "no Secret Service is available (KDE Wallet / GNOME Keyring)",
                hint="enable KDE Wallet in System Settings; NexusOS never stores passwords in plaintext",
            ) from exc
        if collection.is_locked():
            collection.unlock()
            if collection.is_locked():
                raise NexusError("the wallet is locked", hint="unlock KDE Wallet and try again")
        return collection

    def store(self, ref: str, kind: str, secret: str, label: str) -> None:
        collection = self._collection()
        attrs = {"application": APP, "ref": ref, "kind": kind}
        for item in collection.search_items({"application": APP, "ref": ref}):
            item.delete()
        collection.create_item(label, attrs, secret.encode(), replace=True)

    def lookup(self, ref: str) -> str | None:
        for item in self._collection().search_items({"application": APP, "ref": ref}):
            return item.get_secret().decode()
        return None

    def delete(self, ref: str) -> None:
        for item in self._collection().search_items({"application": APP, "ref": ref}):
            item.delete()


class MemoryBackend:
    """In-memory backend for tests only (never used by default)."""

    def __init__(self) -> None:
        self.items: dict[str, str] = {}

    def store(self, ref: str, kind: str, secret: str, label: str) -> None:
        self.items[ref] = secret

    def lookup(self, ref: str) -> str | None:
        return self.items.get(ref)

    def delete(self, ref: str) -> None:
        self.items.pop(ref, None)


class CredentialManager:
    def __init__(self, backend: SecretBackend | None = None, store: Store | None = None) -> None:
        self.backend = backend or SecretServiceBackend()
        self.db = store or default_store()

    def _meta_all(self) -> dict[str, dict]:
        return self.db.get_setting("credentials.meta", {}) or {}

    def list(self) -> list[CredentialMeta]:
        return [CredentialMeta(**m) for m in self._meta_all().values()]

    def save(self, ref: str, kind: Kind, secret: str, username: str = "", rotate_after_days: int | None = None) -> None:
        if not CREDENTIAL_REF_RE.match(ref):
            raise NexusError("invalid credential reference")
        if not secret:
            raise NexusError("empty secret")
        self.backend.store(ref, kind, secret, f"NexusOS {kind} ({ref})")
        meta = self._meta_all()
        meta[ref] = CredentialMeta(
            ref=ref, kind=kind, username=username, created=time.time(), rotate_after_days=rotate_after_days
        ).model_dump()
        self.db.set_setting("credentials.meta", meta)

    def secret(self, ref: str) -> str | None:
        return self.backend.lookup(ref)

    def delete(self, ref: str) -> None:
        self.backend.delete(ref)
        meta = self._meta_all()
        meta.pop(ref, None)
        self.db.set_setting("credentials.meta", meta)

    def due_for_rotation(self) -> list[CredentialMeta]:
        return [m for m in self.list() if m.rotation_due]
