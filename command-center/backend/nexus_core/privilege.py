"""Who the logged-in user is, what they may see, and how administrative tasks run.

The Command Center and the CLI always run as the logged-in user. Administrative
tasks use that user's own ``sudo`` rights and nothing else:

* ``sudo`` without a password (NOPASSWD rule, or credentials cached by sudo)
  → the task runs immediately;
* ``sudo`` with a password → the frontend shows a password box; the password
  goes straight to ``sudo -S`` and is never stored or logged;
* no ``sudo`` → the task is refused ("access denied") and the UI hides or
  disables administrative actions.

``sudo`` only ever starts ``/usr/lib/nexusos/nexus-admin`` (package
nexusos-management-agent), which executes one allow-listed, validated and
audited operation and nothing else.

Classification does not call ``sudo`` (that would write a failed attempt to
the auth log at every start): membership of sudo/admin/wheel marks an
administrator; whether a password is needed is learned the first time an
administrative task runs. Non-members are refused without a password prompt,
unless ``sudo -n`` (a NOPASSWD rule) lets them through.
"""

from __future__ import annotations

import contextlib
import getpass
import grp
import json
import os
import pwd
import queue
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from nexus_core.errors import DependencyMissingError, NexusError

ADMIN_GROUPS = ("sudo", "admin", "wheel")
JOURNAL_GROUPS = ("adm", "systemd-journal")
DEFAULT_HELPER = "/usr/lib/nexusos/nexus-admin"
MAX_ATTEMPTS = 3
AUTH_TIMEOUT_S = 45.0

# Messages of sudo 1.9 (sudo.ws) and sudo-rs, read with LC_ALL=C.
_DENIED = (
    "is not in the sudoers file",
    "is not allowed to",
    "can't do that",
    "may not run sudo",
    "not allowed to execute",
)
_BAD_PASSWORD = ("incorrect password", "authentication failed", "sorry, try again")
_NEEDS_PASSWORD = ("a password is required", "interactive authentication is required", "authentication required")


class AccessDeniedError(NexusError):
    code = "access-denied"


class AuthCancelledError(NexusError):
    code = "cancelled"


class AuthRequiredError(NexusError):
    """A background read needs the password; the UI offers an explicit "Unlock" instead of prompting."""

    code = "auth-required"


class AccessProfile(BaseModel):
    user: str
    uid: int
    full_name: str = ""
    groups: list[str]
    admin: Literal["root", "sudo", "none"]
    auth: Literal["unknown", "required", "not-required"] = "unknown"  # does sudo ask for a password?
    reason: str
    sudo_available: bool
    docker: bool
    journal: bool
    libvirt: bool

    @property
    def can_admin(self) -> bool:
        return self.admin != "none"


@dataclass
class AuthRequest:
    """What the password box shows. ``error`` is set on a retry ("Incorrect password")."""

    user: str
    action: str
    detail: str
    attempt: int
    error: str | None = None


PasswordProvider = Callable[[AuthRequest], "str | None"]
_provider: PasswordProvider | None = None
_profile: AccessProfile | None = None
_profile_lock = threading.Lock()
_auth_lock = threading.Lock()  # one authentication at a time: the second task reuses sudo's cached credentials
_listeners: list[Callable[[], None]] = []


def add_listener(callback: Callable[[], None]) -> None:
    """Called (from any thread) when the profile changes, e.g. after the first authentication."""
    _listeners.append(callback)


def sudo_path() -> str | None:
    return os.environ.get("NEXUSOS_SUDO") or shutil.which("sudo")


def helper_path() -> Path:
    return Path(os.environ.get("NEXUSOS_ADMIN_HELPER", DEFAULT_HELPER))


def set_password_provider(provider: PasswordProvider | None) -> None:
    global _provider
    _provider = provider


def _terminal_provider(req: AuthRequest) -> str | None:
    if req.error:
        sys.stderr.write(f"{req.error}\n")
    try:
        return getpass.getpass(f"[sudo] password for {req.user} ({req.action}): ")
    except (EOFError, KeyboardInterrupt):
        return None


def _current_provider() -> PasswordProvider | None:
    if _provider is not None:
        return _provider
    return _terminal_provider if sys.stdin.isatty() else None


# ------------------------------------------------------------------ profile
def _group_names() -> list[str]:
    names = []
    for gid in sorted(set(os.getgroups()) | {os.getgid()}):
        try:
            names.append(grp.getgrgid(gid).gr_name)
        except KeyError:
            names.append(str(gid))
    return names


def _rw(path: str) -> bool:
    return os.path.exists(path) and os.access(path, os.R_OK | os.W_OK)


def build_profile() -> AccessProfile:
    uid = os.getuid()
    entry = pwd.getpwuid(uid)
    groups = _group_names()
    sudo = sudo_path()
    if uid == 0:
        admin, reason = "root", "running as root"
    elif sudo is None:
        admin, reason = "none", "sudo is not installed"
    elif set(groups) & set(ADMIN_GROUPS):
        admin, reason = "sudo", f"member of '{next(g for g in groups if g in ADMIN_GROUPS)}' (sudo)"
    else:
        admin, reason = "none", "not a member of the sudo group"
    return AccessProfile(
        user=entry.pw_name,
        uid=uid,
        full_name=(entry.pw_gecos or "").split(",")[0],
        groups=groups,
        admin=admin,  # type: ignore[arg-type]
        auth="not-required" if uid == 0 else "unknown",
        reason=reason,
        sudo_available=sudo is not None,
        docker=uid == 0 or _rw("/var/run/docker.sock"),
        journal=uid == 0 or bool(set(groups) & set(JOURNAL_GROUPS)),
        libvirt=uid == 0 or "libvirt" in groups or _rw("/var/run/libvirt/libvirt-sock"),
    )


def access(refresh: bool = False) -> AccessProfile:
    global _profile
    with _profile_lock:
        if _profile is None or refresh:
            learned = _profile.auth if _profile is not None else "unknown"
            _profile = build_profile()
            if _profile.auth == "unknown":
                _profile.auth = learned  # type: ignore[assignment]
        return _profile


def _learn(mode: Literal["required", "not-required"], admin: Literal["sudo"] | None = None) -> None:
    with _profile_lock:
        if _profile is not None:
            if _profile.auth != "required":  # -n may succeed on cached credentials: keep "required"
                _profile.auth = mode
            if admin:
                _profile.admin = admin
                _profile.reason = "sudo rule for this user"
    for callback in list(_listeners):
        with contextlib.suppress(Exception):
            callback()


def require_admin(action: str = "this task") -> AccessProfile:
    profile = access()
    if not profile.can_admin:
        raise AccessDeniedError(
            f"Access denied: {profile.user} cannot perform {action}",
            hint=f"administrative tasks need sudo rights ({profile.reason})",
        )
    return profile


# ------------------------------------------------------------------ sudo session
def _matches(text: str, needles: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(n.lower() in low for n in needles)


class SudoSession:
    """One administrative operation through ``sudo nexus-admin run``.

    Same interface as :class:`nexus_core.agent_client.AgentSession`: iterate
    :meth:`events`, call :meth:`cancel` from another thread.
    """

    def __init__(
        self, op: str, params: dict[str, Any] | None = None, *, label: str | None = None, prompt: bool = True
    ) -> None:
        self.op, self.label = op, label or op
        self.request = json.dumps({"v": 1, "op": op, "params": params or {}}) + "\n"
        self.proc: subprocess.Popen[str] | None = None
        self._stderr: list[str] = []
        profile = access()
        helper = helper_path()
        if not helper.exists():
            raise DependencyMissingError(
                "the NexusOS admin helper is not installed", hint="install nexusos-management-agent"
            )
        if profile.uid == 0:
            self._start([str(helper), "run"], None)
            return
        sudo = sudo_path()
        if sudo is None:
            raise AccessDeniedError("Access denied: sudo is not installed", hint="administrative tasks need sudo")
        with _auth_lock:
            outcome = self._start([sudo, "-n", "--", str(helper), "run"], None)
            if outcome == "ok":
                _learn("not-required", "sudo" if profile.admin == "none" else None)
                return
            if outcome == "denied" or (outcome == "needs-password" and not profile.can_admin):
                raise self._denied(profile)
            if outcome != "needs-password":
                raise NexusError("could not start the admin helper", hint=" ".join(self._stderr[-3:]) or None)
            if not prompt:
                raise AuthRequiredError(f"{self.label} needs the administrator password")
            self._authenticate(sudo, helper, profile)

    # -------------------------------------------------------------- start
    def _start(self, argv: list[str], password: str | None) -> str:
        """Start the helper; return 'ok', 'denied', 'bad-password', 'needs-password' or 'failed'."""
        env = {"LC_ALL": "C", "LANG": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}
        self._stderr = []
        proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, bufsize=1
        )
        signals: queue.Queue[tuple[str, str | None]] = queue.Queue()

        def first_line() -> None:
            signals.put(("out", proc.stdout.readline() or None))

        def errors() -> None:
            for line in proc.stderr:
                if len(self._stderr) < 200:
                    self._stderr.append(line.rstrip())
                signals.put(("err", line))
            signals.put(("err-eof", None))

        threading.Thread(target=first_line, daemon=True).start()
        threading.Thread(target=errors, daemon=True).start()
        if password is not None:
            with contextlib.suppress(BrokenPipeError, OSError):
                proc.stdin.write(password + "\n")
                proc.stdin.flush()
        outcome = "failed"
        while True:
            try:
                kind, text = signals.get(timeout=AUTH_TIMEOUT_S)
            except queue.Empty:
                break
            if kind == "out":
                if text and '"hello"' in text:
                    self.proc = proc
                    with contextlib.suppress(BrokenPipeError, OSError):
                        proc.stdin.write(self.request)
                        proc.stdin.flush()
                    return "ok"
                if text:  # the helper itself refused (e.g. not root)
                    self._stderr.append(text.strip())
                continue
            if kind == "err" and text:
                if _matches(text, _DENIED):
                    outcome = "denied"
                    break
                if _matches(text, _BAD_PASSWORD):
                    outcome = "bad-password"
                    break  # sudo waits for another line: stop it instead
                if _matches(text, _NEEDS_PASSWORD):
                    outcome = "needs-password"
            if kind == "err-eof":
                break
        self._stop(proc)
        return outcome

    @staticmethod
    def _stop(proc: subprocess.Popen[str]) -> None:
        with contextlib.suppress(OSError):
            proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    def _denied(self, profile: AccessProfile) -> AccessDeniedError:
        detail = next((line for line in self._stderr if _matches(line, _DENIED)), profile.reason)
        return AccessDeniedError(
            f"Access denied: {profile.user} may not perform administrative tasks",
            hint=f"{detail.removeprefix('sudo: ')} — ask an administrator to add you to the 'sudo' group",
        )

    def _authenticate(self, sudo: str, helper: Path, profile: AccessProfile) -> None:
        provider = _current_provider()
        if provider is None:
            raise AccessDeniedError(
                f"{self.label} needs the administrator password",
                hint="run it from the Command Center or an interactive terminal",
            )
        error: str | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            password = provider(AuthRequest(profile.user, self.label, self.op, attempt, error))
            if password is None:
                raise AuthCancelledError("Authentication cancelled", hint=f"{self.label} was not performed")
            outcome = self._start([sudo, "-S", "-p", "", "--", str(helper), "run"], password)
            del password
            if outcome == "ok":
                _learn("required")
                return
            if outcome == "denied":
                raise self._denied(profile)
            if outcome != "bad-password":
                raise NexusError("sudo failed", hint=" ".join(self._stderr[-3:]) or None)
            error = "Incorrect password, try again"
        raise AccessDeniedError("Authentication failed", hint=f"{MAX_ATTEMPTS} incorrect password attempts")

    # -------------------------------------------------------------- protocol
    def events(self) -> Iterator[dict[str, Any]]:
        from nexus_core.agent_client import MAX_MESSAGE, AgentError

        try:
            for line in self.proc.stdout:
                if len(line) > MAX_MESSAGE:
                    raise NexusError("oversized message from nexus-admin")
                event = json.loads(line)
                if event.get("type") == "error":
                    raise AgentError(event.get("code", "error"), event.get("message", "admin helper error"))
                yield event
                if event.get("type") == "result":
                    return
        finally:
            self.close()
        raise NexusError("nexus-admin ended without a result", hint=" ".join(self._stderr[-3:]) or None)

    def cancel(self) -> None:
        if self.proc is not None and self.proc.stdin is not None:
            with contextlib.suppress(BrokenPipeError, OSError, ValueError):
                self.proc.stdin.write('{"type": "cancel"}\n')
                self.proc.stdin.flush()

    def close(self) -> None:
        if self.proc is not None:
            self._stop(self.proc)
