"""SSH connection profiles (stored in the local SQLite store; never contain secrets)."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from nexus_core import validation
from nexus_core.errors import NexusError, ValidationError
from nexus_core.store import Store, default_store, now

GROUPS = ("Favorites", "Production", "Development", "Homelab", "Cloud servers", "Custom")
CREDENTIAL_REF_RE = re.compile(r"^[a-z0-9][a-z0-9._\-]{0,63}$")

# OpenSSH options a profile may set. Anything else is rejected (no ProxyCommand/LocalCommand injection).
ALLOWED_OPTIONS = {
    "ServerAliveInterval": re.compile(r"^\d{1,4}$"),
    "ServerAliveCountMax": re.compile(r"^\d{1,3}$"),
    "ConnectTimeout": re.compile(r"^\d{1,4}$"),
    "Compression": re.compile(r"^(yes|no)$"),
    "StrictHostKeyChecking": re.compile(r"^(yes|ask|accept-new)$"),
    "IdentitiesOnly": re.compile(r"^(yes|no)$"),
    "PreferredAuthentications": re.compile(r"^[a-z\-,]{1,100}$"),
    "PubkeyAcceptedAlgorithms": re.compile(r"^[A-Za-z0-9@.,+\-]{1,300}$"),
    "HostKeyAlgorithms": re.compile(r"^[A-Za-z0-9@.,+\-]{1,300}$"),
    "RequestTTY": re.compile(r"^(yes|no|force|auto)$"),
    "SetEnv": re.compile(r"^(TERM|LANG|LC_[A-Z]+)=[A-Za-z0-9._\-]{1,40}$"),
}


class Forward(BaseModel):
    kind: Literal["local", "remote", "dynamic"]
    bind_address: str = "127.0.0.1"
    listen_port: int
    dest_host: str | None = None
    dest_port: int | None = None

    @model_validator(mode="after")
    def _check(self) -> Forward:
        validation.port(self.listen_port)
        validation.host_or_ip(self.bind_address)
        if self.kind == "dynamic":
            if self.dest_host or self.dest_port:
                raise ValueError("SOCKS (dynamic) forwards have no destination")
        else:
            if not self.dest_host or not self.dest_port:
                raise ValueError("local/remote forwards need a destination host and port")
            validation.host_or_ip(self.dest_host)
            validation.port(self.dest_port)
        return self

    def ssh_option(self) -> tuple[str, str]:
        bind = f"[{self.bind_address}]" if ":" in self.bind_address else self.bind_address
        if self.kind == "dynamic":
            return "DynamicForward", f"{bind}:{self.listen_port}"
        key = "LocalForward" if self.kind == "local" else "RemoteForward"
        dest = f"[{self.dest_host}]" if self.dest_host and ":" in self.dest_host else self.dest_host
        return key, f"{bind}:{self.listen_port} {dest}:{self.dest_port}"


class SSHProfile(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    host: str
    port: int = 22
    user: str
    auth: Literal["agent", "key", "password"] = "agent"
    key_path: str | None = None
    credential_ref: str | None = None
    jump_profile_id: str | None = None
    agent_forwarding: bool = False
    agent_forwarding_consent: float | None = None
    forwards: list[Forward] = Field(default_factory=list)
    options: dict[str, str] = Field(default_factory=dict)
    group: str = "Custom"
    tags: list[str] = Field(default_factory=list)
    favorite: bool = False
    konsole_profile: str = "Nexus"
    reconnect_on_restore: bool = False
    notes: str = ""

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return validation.display_name(v)

    @field_validator("host")
    @classmethod
    def _host(cls, v: str) -> str:
        return validation.host_or_ip(v)

    @field_validator("port")
    @classmethod
    def _port(cls, v: int) -> int:
        return validation.port(v)

    @field_validator("user")
    @classmethod
    def _user(cls, v: str) -> str:
        return validation.ssh_user(v)

    @field_validator("credential_ref")
    @classmethod
    def _ref(cls, v: str | None) -> str | None:
        if v is not None and not CREDENTIAL_REF_RE.match(v):
            raise ValueError("credential reference: lowercase letters, digits, '.', '_', '-'")
        return v

    @field_validator("key_path")
    @classmethod
    def _key(cls, v: str | None) -> str | None:
        if v is None:
            return None
        validation.single_line(v, max_len=4096, field="key path")
        if v.endswith(".pub"):
            raise ValueError("select the private key file, not the .pub file")
        return v

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return [validation.display_name(t) for t in v][:20]

    @field_validator("group")
    @classmethod
    def _group(cls, v: str) -> str:
        return validation.display_name(v)

    @field_validator("notes")
    @classmethod
    def _notes(cls, v: str) -> str:
        if len(v) > 2000:
            raise ValueError("notes too long")
        return v

    @field_validator("options")
    @classmethod
    def _options(cls, v: dict[str, str]) -> dict[str, str]:
        for key, value in v.items():
            pattern = ALLOWED_OPTIONS.get(key)
            if pattern is None:
                raise ValueError(f"SSH option {key!r} is not allowed in profiles")
            if not pattern.match(str(value)):
                raise ValueError(f"invalid value for {key}: {value!r}")
        return v

    @model_validator(mode="after")
    def _auth(self) -> SSHProfile:
        if self.auth == "key" and not self.key_path:
            raise ValueError("key authentication requires a key file")
        if self.auth == "password" and not self.credential_ref:
            raise ValueError("password authentication requires a saved credential reference")
        if self.agent_forwarding and not self.agent_forwarding_consent:
            raise ValueError("agent forwarding requires explicit consent (it lets the remote host use your keys)")
        return self

    @property
    def alias(self) -> str:
        return f"nexus-{self.id}"


def _row_to_profile(row) -> SSHProfile:
    return SSHProfile(**json.loads(row["data"]))


def save(profile: SSHProfile, store: Store | None = None) -> SSHProfile:
    store = store or default_store()
    if profile.jump_profile_id:
        if profile.jump_profile_id == profile.id:
            raise ValidationError("a profile cannot be its own jump host")
        get(profile.jump_profile_id, store)
        chain, current = {profile.id}, profile.jump_profile_id
        while current:
            if current in chain:
                raise ValidationError("jump host chain contains a loop")
            chain.add(current)
            current = get(current, store).jump_profile_id
    if profile.key_path and not Path(profile.key_path).expanduser().is_file():
        raise ValidationError(f"key file not found: {profile.key_path}")
    ts = now()
    store.execute(
        "INSERT INTO ssh_profiles(id, name, data, favorite, grp, created, updated) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, data=excluded.data, favorite=excluded.favorite, "
        "grp=excluded.grp, updated=excluded.updated",
        (profile.id, profile.name, profile.model_dump_json(), int(profile.favorite), profile.group, ts, ts),
    )
    return profile


def get(profile_id_or_name: str, store: Store | None = None) -> SSHProfile:
    store = store or default_store()
    rows = store.query("SELECT data FROM ssh_profiles WHERE id=? OR name=?", (profile_id_or_name, profile_id_or_name))
    if not rows:
        raise NexusError(f"no SSH profile {profile_id_or_name!r}", hint="list profiles with `nexus ssh list`")
    return _row_to_profile(rows[0])


def delete(profile_id: str, store: Store | None = None) -> None:
    store = store or default_store()
    profile = get(profile_id, store)
    dependants = [p.name for p in list_profiles(store=store) if p.jump_profile_id == profile.id]
    if dependants:
        raise ValidationError(f"{profile.name} is the jump host for: {', '.join(dependants)}")
    store.execute("DELETE FROM ssh_profiles WHERE id=?", (profile.id,))


def list_profiles(
    query: str = "", group: str | None = None, favorites_only: bool = False, store: Store | None = None
) -> list[SSHProfile]:
    store = store or default_store()
    profiles = [_row_to_profile(r) for r in store.query("SELECT data FROM ssh_profiles ORDER BY favorite DESC, name")]
    q = query.lower().strip()
    out = []
    for p in profiles:
        if favorites_only and not p.favorite:
            continue
        if group and p.group != group:
            continue
        haystack = " ".join([p.name, p.host, p.user, p.group, *p.tags]).lower()
        if q and q not in haystack:
            continue
        out.append(p)
    return out


def record_event(profile_id: str, event: str, store: Store | None = None) -> None:
    store = store or default_store()
    store.execute("INSERT INTO ssh_history(profile_id, ts, event) VALUES (?,?,?)", (profile_id, now(), event[:200]))
    store.trim("ssh_history")


def history(limit: int = 50, store: Store | None = None) -> list[dict]:
    store = store or default_store()
    rows = store.query(
        "SELECT h.ts, h.event, h.profile_id, p.name FROM ssh_history h LEFT JOIN ssh_profiles p ON p.id=h.profile_id "
        "ORDER BY h.id DESC LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in rows]


def recent(limit: int = 10, store: Store | None = None) -> list[SSHProfile]:
    store = store or default_store()
    rows = store.query(
        "SELECT profile_id, MAX(ts) AS last FROM ssh_history WHERE event='connect' GROUP BY profile_id "
        "ORDER BY last DESC LIMIT ?",
        (limit,),
    )
    out = []
    for r in rows:
        try:
            out.append(get(r["profile_id"], store))
        except NexusError:
            continue
    return out
