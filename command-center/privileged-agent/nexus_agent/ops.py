"""Allow-listed privileged operations.

Every operation declares the polkit action that protects it and a Pydantic model
that validates its parameters. Nothing outside this table can be executed, and no
operation accepts a command line, a shell fragment or an arbitrary path to write.
"""

from __future__ import annotations

import fcntl
import os
import re
import selectors
import signal
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from nexus_core import packages, paths, runner, validation
from nexus_core.errors import NexusError, ValidationError
from nexus_core.gateway import apply as gw_apply
from nexus_core.gateway import certs as gw_certs
from nexus_core.gateway.model import ROUTE_ID_RE, Route, dump_route
from nexus_core.redact import redact_text
from pydantic import BaseModel, Field, field_validator

ACTION_PACKAGES = "org.nexusos.agent.packages.manage"
ACTION_REPOS = "org.nexusos.agent.packages.repositories"
ACTION_GATEWAY = "org.nexusos.agent.gateway.manage"
ACTION_GATEWAY_LOGS = "org.nexusos.agent.gateway.logs"
ACTION_STORAGE_READ = "org.nexusos.agent.storage.read"
ACTION_FIREWALL_READ = "org.nexusos.agent.firewall.read"
ACTION_FIREWALL = "org.nexusos.agent.firewall.manage"

APT_ENV = {
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "DEBIAN_FRONTEND": "noninteractive",
    "APT_LISTCHANGES_FRONTEND": "none",
    "LC_ALL": "C.UTF-8",
}
DPKG_SAFE_OPTS = ["-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold"]
_STATUS_RE = re.compile(r"^(dlstatus|pmstatus|pmerror|pmconffile|media-change):([^:]*):([0-9.]+):(.*)$")

_apt_lock = threading.Lock()


@dataclass
class Context:
    emit: Callable[[dict[str, Any]], None]
    cancelled: threading.Event
    uid: int


class Op:
    def __init__(
        self, name: str, action: str | None, model: type[BaseModel], handler: Callable[[Any, Context], dict[str, Any]]
    ) -> None:
        self.name, self.action, self.model, self.handler = name, action, model, handler


REGISTRY: dict[str, Op] = {}


def op(name: str, action: str | None, model: type[BaseModel]):
    def deco(fn):
        REGISTRY[name] = Op(name, action, model, fn)
        return fn

    return deco


class NoParams(BaseModel):
    model_config = {"extra": "forbid"}


# ===================================================================== agent
@op("agent.ping", None, NoParams)
def _ping(_: NoParams, ctx: Context) -> dict[str, Any]:
    from nexus_agent import __version__

    return {"version": __version__, "operations": sorted(REGISTRY)}


# ===================================================================== APT
class AptParams(BaseModel):
    model_config = {"extra": "forbid"}
    packages: list[str] = Field(default_factory=list)
    expected: list[str] | None = Field(default=None, description="'action:name' list the user confirmed")

    @field_validator("packages")
    @classmethod
    def _names(cls, v: list[str]) -> list[str]:
        return [validation.package_name(n) for n in v]


def _dpkg_locked() -> str | None:
    for lock in (Path("/var/lib/dpkg/lock-frontend"), Path("/var/lib/dpkg/lock")):
        try:
            fd = os.open(lock, os.O_RDWR)
        except OSError:
            continue
        try:
            fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.lockf(fd, fcntl.LOCK_UN)
        except OSError:
            status = packages.lock_status()
            return f"{lock} held by {status.holder_name or 'another process'} (pid {status.holder_pid or '?'})"
        finally:
            os.close(fd)
    return None


def run_apt(command: list[str], ctx: Context) -> dict[str, Any]:
    """Run apt-get with machine-readable progress on a status fd; cancellable during download only."""
    read_fd, write_fd = os.pipe()
    argv = [*command[:1], "-o", f"APT::Status-Fd={write_fd}", *DPKG_SAFE_OPTS, *command[1:]]
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        pass_fds=(write_fd,),
        env=APT_ENV,
        stdin=subprocess.DEVNULL,
    )
    os.close(write_fd)
    if proc.stdout is None:
        raise NexusError("apt-get output unavailable")
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ, "out")
    selector.register(read_fd, selectors.EVENT_READ, "status")
    phase = "prepare"
    tail: list[str] = []
    buffers = {"out": b"", "status": b""}
    cancel_sent = False
    open_streams = 2
    while open_streams:
        if ctx.cancelled.is_set() and not cancel_sent:
            if phase in ("prepare", "download"):
                proc.send_signal(signal.SIGINT)
                cancel_sent = True
                ctx.emit({"type": "log", "line": "cancel requested: stopping before any package is changed"})
            else:
                ctx.emit({"type": "log", "line": "cancel refused: dpkg is changing the system; waiting to finish"})
                ctx.cancelled.clear()
        for key, _ in selector.select(timeout=0.5):
            fd = key.fileobj if key.data == "status" else key.fileobj.fileno()
            chunk = os.read(fd, 65536)
            if not chunk:
                selector.unregister(key.fileobj)
                open_streams -= 1
                continue
            buffers[key.data] += chunk
            *lines, buffers[key.data] = buffers[key.data].split(b"\n")
            for raw in lines:
                line = raw.decode("utf-8", "replace")
                if key.data == "out":
                    line = redact_text(line)
                    tail = [*tail, line][-40:]
                    ctx.emit({"type": "log", "line": line})
                    continue
                m = _STATUS_RE.match(line)
                if not m:
                    continue
                kind, pkg, pct, msg = m.groups()
                if kind == "dlstatus":
                    phase = "download"
                elif kind == "pmstatus":
                    phase = "install"
                elif kind == "pmerror":
                    ctx.emit({"type": "log", "line": f"error: {pkg}: {msg}"})
                    continue
                ctx.emit({"type": "progress", "phase": phase, "percent": float(pct), "package": pkg, "message": msg})
    os.close(read_fd)
    code = proc.wait()
    if cancel_sent and code != 0:
        return {"ok": False, "cancelled": True, "exit_code": code}
    if code != 0:
        raise NexusError(
            f"apt-get exited with status {code}",
            hint=next((ln for ln in reversed(tail) if ln.startswith(("E:", "dpkg:"))), None),
        )
    return {"ok": True, "exit_code": code}


def _apt_operation(operation: packages.Operation, params: AptParams, ctx: Context) -> dict[str, Any]:
    if operation in ("install", "remove", "purge") and not params.packages:
        raise ValidationError("no packages given")
    if not _apt_lock.acquire(blocking=False):
        raise AgentBusyError("another package operation is already running")
    try:
        locked = _dpkg_locked()
        if locked:
            raise AgentLockedError(f"package manager is locked: {locked}")
        if operation != "update" and params.expected is not None:
            fresh = packages.plan(operation, params.packages)
            current = sorted(f"{c.action}:{c.name}" for c in fresh.changes)
            if current != sorted(params.expected):
                raise ValidationError("the planned changes differ from what was confirmed; review the plan again")
        command = packages.build_command(operation, params.packages)
        ctx.emit({"type": "log", "line": "running: " + " ".join(command)})
        return run_apt(command, ctx)
    finally:
        _apt_lock.release()


class AgentBusyError(NexusError):
    code = "busy"


class AgentLockedError(NexusError):
    code = "locked"


for _op in ("update", "install", "remove", "purge", "upgrade", "full-upgrade"):

    def _make(operation: str):
        def handler(params: AptParams, ctx: Context) -> dict[str, Any]:
            return _apt_operation(operation, params, ctx)  # type: ignore[arg-type]

        return handler

    op(f"apt.{_op}", ACTION_PACKAGES, AptParams)(_make(_op))


class RepoAdd(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    uri: str
    suites: list[str]
    components: list[str] = Field(default_factory=list)
    signed_by: str


class RepoRemove(BaseModel):
    model_config = {"extra": "forbid"}
    name: str


@op("apt.repo.add", ACTION_REPOS, RepoAdd)
def _repo_add(p: RepoAdd, ctx: Context) -> dict[str, Any]:
    text = packages.validate_repository(p.name, p.uri, p.suites, p.components, p.signed_by)
    if not Path(p.signed_by).is_file():
        raise ValidationError(f"keyring {p.signed_by} does not exist; install the repository key first")
    target = packages.SOURCES_DIR / f"nexusos-{p.name}.sources"
    target.write_text(text)
    os.chmod(target, 0o644)
    return {"file": str(target)}


@op("apt.repo.remove", ACTION_REPOS, RepoRemove)
def _repo_remove(p: RepoRemove, ctx: Context) -> dict[str, Any]:
    if not packages.REPO_NAME_RE.match(p.name):
        raise ValidationError("invalid repository name")
    target = packages.SOURCES_DIR / f"nexusos-{p.name}.sources"
    if not target.exists():
        raise ValidationError(f"no NexusOS-managed repository named {p.name}")
    target.unlink()
    return {"removed": str(target)}


# ===================================================================== gateway
def _gateway_env() -> gw_apply.GatewayEnv:
    return gw_apply.GatewayEnv(
        gateway_dir=paths.gateway_dir(),
        nginx_test=tuple(os.environ.get("NEXUSOS_NGINX_TEST", "nginx -t -q").split()),
        nginx_reload=tuple(os.environ.get("NEXUSOS_NGINX_RELOAD", "systemctl reload nginx").split()),
    )


class RouteSave(BaseModel):
    model_config = {"extra": "forbid"}
    route: dict[str, Any]


class RouteId(BaseModel):
    model_config = {"extra": "forbid"}
    id: str

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not ROUTE_ID_RE.match(v):
            raise ValueError("invalid route id")
        return v


@op("gateway.route.save", ACTION_GATEWAY, RouteSave)
def _route_save(p: RouteSave, ctx: Context) -> dict[str, Any]:
    route = Route(**p.route)
    route.check_backend()
    env = _gateway_env()
    gw_apply.ensure_layout(env)
    target = env.routes_dir / f"{route.id}.yaml"
    target.write_text(dump_route(route))
    os.chmod(target, 0o644)
    return {"saved": route.id, "approved": route.approved}


@op("gateway.route.delete", ACTION_GATEWAY, RouteId)
def _route_delete(p: RouteId, ctx: Context) -> dict[str, Any]:
    target = _gateway_env().routes_dir / f"{p.id}.yaml"
    if not target.exists():
        raise ValidationError(f"no route {p.id}")
    target.unlink()
    return {"deleted": p.id}


@op("gateway.apply", ACTION_GATEWAY, NoParams)
def _gateway_apply(_: NoParams, ctx: Context) -> dict[str, Any]:
    result = gw_apply.apply(_gateway_env())
    return result.__dict__


@op("gateway.rollback", ACTION_GATEWAY, NoParams)
def _gateway_rollback(_: NoParams, ctx: Context) -> dict[str, Any]:
    return gw_apply.rollback(_gateway_env()).__dict__


@op("gateway.nginx.test", ACTION_GATEWAY, NoParams)
def _nginx_test(_: NoParams, ctx: Context) -> dict[str, Any]:
    result = runner.run(list(_gateway_env().nginx_test), timeout=30)
    return {"ok": result.ok, "output": (result.stdout + result.stderr).strip()}


@op("gateway.nginx.reload", ACTION_GATEWAY, NoParams)
def _nginx_reload(_: NoParams, ctx: Context) -> dict[str, Any]:
    env = _gateway_env()
    test = runner.run(list(env.nginx_test), timeout=30)
    if not test.ok:
        return {"ok": False, "output": (test.stdout + test.stderr).strip(), "message": "nginx -t failed; not reloaded"}
    result = runner.run(list(env.nginx_reload), timeout=60)
    return {"ok": result.ok, "output": result.stderr.strip()}


class CertIssue(BaseModel):
    model_config = {"extra": "forbid"}
    mode: Literal["self-signed", "internal-ca", "letsencrypt"]
    name: str
    hostnames: list[str]
    email: str | None = None
    staging: bool = False

    @field_validator("hostnames")
    @classmethod
    def _hosts(cls, v: list[str]) -> list[str]:
        if not v or len(v) > 20:
            raise ValueError("1-20 hostnames required")
        return [validation.hostname(h, allow_wildcard=True) for h in v]


@op("gateway.cert.issue", ACTION_GATEWAY, CertIssue)
def _cert_issue(p: CertIssue, ctx: Context) -> dict[str, Any]:
    gdir = paths.gateway_dir()
    gw_apply.ensure_layout(_gateway_env())
    if p.mode == "self-signed":
        path = gw_certs.issue_self_signed(gdir, p.name, p.hostnames)
    elif p.mode == "internal-ca":
        path = gw_certs.issue_internal(gdir, p.name, p.hostnames)
    else:
        gw_certs.issue_letsencrypt(gdir, p.hostnames[0], p.email or "", p.staging)
        path = gw_certs.LETSENCRYPT_LIVE / p.hostnames[0]
    return {"path": str(path)}


class CertImport(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    cert_file: str
    key_file: str


@op("gateway.cert.import", ACTION_GATEWAY, CertImport)
def _cert_import(p: CertImport, ctx: Context) -> dict[str, Any]:
    # Source files must be readable by the *calling user* too, so users cannot import files they cannot read.
    for f in (p.cert_file, p.key_file):
        st = os.stat(f)
        if st.st_uid != ctx.uid and not (st.st_mode & 0o004):
            raise ValidationError(f"{f} is not owned by or readable for the requesting user")
    path = gw_certs.import_certificate(paths.gateway_dir(), p.name, Path(p.cert_file), Path(p.key_file))
    return {"path": str(path)}


@op("gateway.cert.renew", ACTION_GATEWAY, NoParams)
def _cert_renew(_: NoParams, ctx: Context) -> dict[str, Any]:
    return {"renewed": gw_certs.renew_due(paths.gateway_dir())}


class LogParams(BaseModel):
    model_config = {"extra": "forbid"}
    kind: Literal["access", "error"] = "error"
    lines: int = 200


@op("gateway.logs", ACTION_GATEWAY_LOGS, LogParams)
def _gateway_logs(p: LogParams, ctx: Context) -> dict[str, Any]:
    log = Path(f"/var/log/nginx/{p.kind}.log")
    if not log.exists():
        return {"lines": []}
    lines = log.read_text(errors="replace").splitlines()[-max(1, min(p.lines, 2000)) :]
    return {"lines": [redact_text(ln) for ln in lines]}


# ===================================================================== storage / firewall
class SmartParams(BaseModel):
    model_config = {"extra": "forbid"}
    device: str

    @field_validator("device")
    @classmethod
    def _dev(cls, v: str) -> str:
        if not re.fullmatch(r"/dev/(sd[a-z]{1,2}|nvme[0-9]+n[0-9]+|vd[a-z]{1,2}|hd[a-z])", v):
            raise ValueError("device must be a whole-disk node like /dev/sda or /dev/nvme0n1")
        return v


@op("storage.smart", ACTION_STORAGE_READ, SmartParams)
def _smart(p: SmartParams, ctx: Context) -> dict[str, Any]:
    import json

    result = runner.run(["smartctl", "-j", "-a", p.device], timeout=60)
    if not result.found:
        raise NexusError("smartctl not found", hint="sudo apt install smartmontools")
    try:
        data = json.loads(result.stdout or "{}")
    except ValueError:
        data = {}
    return {"smart": data, "exit_code": result.returncode}


@op("firewall.status", ACTION_FIREWALL_READ, NoParams)
def _fw_status(_: NoParams, ctx: Context) -> dict[str, Any]:
    result = runner.run(["ufw", "status", "verbose"], timeout=20)
    if not result.found:
        return {"installed": False, "output": ""}
    return {"installed": True, "output": result.stdout.strip()}


class FirewallParams(BaseModel):
    model_config = {"extra": "forbid"}
    action: Literal["enable", "disable", "allow", "deny", "delete-allow"]
    port: int | None = None
    proto: Literal["tcp", "udp"] = "tcp"
    from_lan_only: bool = True


@op("firewall.set", ACTION_FIREWALL, FirewallParams)
def _fw_set(p: FirewallParams, ctx: Context) -> dict[str, Any]:
    if p.action in ("enable", "disable"):
        cmd = ["ufw", "--force", p.action]
    else:
        port = validation.port(p.port or 0)
        rule = "allow" if p.action == "delete-allow" else p.action
        target = (
            ["from", "192.168.0.0/16", "to", "any", "port", str(port), "proto", p.proto]
            if p.from_lan_only and rule == "allow"
            else [f"{port}/{p.proto}"]
        )
        cmd = ["ufw", *(["delete"] if p.action == "delete-allow" else []), rule, *target]
    result = runner.run(cmd, timeout=30)
    if not result.ok:
        raise NexusError("ufw failed", hint=runner.first_line(result.stderr or result.stdout))
    return {"output": result.stdout.strip()}
