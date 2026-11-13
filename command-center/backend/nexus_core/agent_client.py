"""Client for the NexusOS management agent (privileged helper).

Protocol (version 1): newline-delimited JSON over the Unix socket
``/run/nexusos/agent.sock``.

  client -> agent   {"v": 1, "op": "apt.install", "params": {...}}
  agent  -> client  {"type": "progress", "phase": "download", "percent": 42.0, "message": "..."}
                    {"type": "log", "line": "..."}
                    {"type": "result", "ok": true, "data": {...}}
                    {"type": "error", "code": "unauthorized", "message": "..."}
  client -> agent   {"type": "cancel"}          (optional, while an operation runs)

The agent authenticates the caller with SO_PEERCRED and authorizes every
operation with polkit. The frontends never receive root privileges.
"""

from __future__ import annotations

import contextlib
import json
import socket
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from nexus_core import paths
from nexus_core.errors import DependencyMissingError, NexusError

PROTOCOL_VERSION = 1
MAX_MESSAGE = 4 * 1024 * 1024


class AgentUnavailableError(DependencyMissingError):
    def __init__(self, socket_path: Path) -> None:
        super().__init__(
            f"NexusOS management agent is not available at {socket_path}",
            hint="install nexusos-management-agent (systemctl status nexusos-agent.socket)",
        )


class AgentError(NexusError):
    def __init__(self, code: str, message: str) -> None:
        hints = {
            "unauthorized": "authorization was denied or cancelled (polkit)",
            "busy": "another package operation is running; wait for it to finish",
            "locked": "the package manager is locked by another program",
        }
        super().__init__(message, hint=hints.get(code))
        self.code = code


class AgentSession:
    """One request/response exchange. Iterate :meth:`events`; call :meth:`cancel` from another thread."""

    def __init__(
        self,
        op: str,
        params: dict[str, Any] | None = None,
        socket_path: Path | None = None,
        timeout: float | None = None,
    ) -> None:
        self.socket_path = socket_path or paths.agent_socket()
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(timeout)
        try:
            self._sock.connect(str(self.socket_path))
        except (FileNotFoundError, ConnectionRefusedError) as exc:
            self._sock.close()
            raise AgentUnavailableError(self.socket_path) from exc
        except PermissionError as exc:
            self._sock.close()
            raise NexusError(
                "permission denied connecting to the management agent",
                hint="administrative operations are limited to members of the 'sudo' group",
            ) from exc
        payload = json.dumps({"v": PROTOCOL_VERSION, "op": op, "params": params or {}}) + "\n"
        self._sock.sendall(payload.encode())
        self._file = self._sock.makefile("r", encoding="utf-8")

    def events(self) -> Iterator[dict[str, Any]]:
        try:
            for line in self._file:
                if len(line) > MAX_MESSAGE:
                    raise NexusError("oversized message from agent")
                event = json.loads(line)
                if event.get("type") == "error":
                    raise AgentError(event.get("code", "error"), event.get("message", "agent error"))
                yield event
                if event.get("type") == "result":
                    return
        finally:
            self.close()
        raise NexusError("the management agent closed the connection without a result")

    def cancel(self) -> None:
        with contextlib.suppress(OSError):
            self._sock.sendall(b'{"type": "cancel"}\n')

    def close(self) -> None:
        try:
            self._file.close()
        finally:
            self._sock.close()


def call(
    op: str,
    params: dict[str, Any] | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    socket_path: Path | None = None,
) -> dict[str, Any]:
    """Run an operation to completion and return the result's ``data``."""
    session = AgentSession(op, params, socket_path)
    for event in session.events():
        if event.get("type") == "result":
            return event.get("data") or {}
        if on_event:
            on_event(event)
    raise NexusError("no result from agent")


def available(socket_path: Path | None = None) -> bool:
    return (socket_path or paths.agent_socket()).exists()
