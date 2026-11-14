"""Run one allow-listed operation: validate, authorize, execute, audit, report.

Shared by the socket agent (polkit authorization) and ``nexus-admin`` (the
helper the Command Center starts through ``sudo``; sudo has already authorized
the caller). Events are newline-delimited JSON (see nexus_core.agent_client).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from nexus_core.errors import NexusError, ValidationError
from pydantic import ValidationError as PydanticValidationError

from nexus_agent import audit, ops

Send = Callable[[dict[str, Any]], None]
Authorize = Callable[[str], tuple[bool, str]]


def parse_request(request: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(request, dict) or request.get("v") != 1:
        raise ValueError("malformed request")
    name, params = request.get("op"), request.get("params") or {}
    if not isinstance(name, str) or not isinstance(params, dict):
        raise ValueError("malformed request")
    return name, params


def execute(
    name: str,
    params: dict[str, Any],
    *,
    send: Send,
    cancelled: threading.Event,
    uid: int,
    pid: int,
    authorize: Authorize | None,
    via: str,
) -> None:
    """Execute *name* and send exactly one ``result`` or ``error`` event."""
    operation = ops.REGISTRY.get(name)
    if operation is None:
        audit.record(uid, pid, name[:64], {}, "rejected", "unknown op", via=via)
        send({"type": "error", "code": "unknown-op", "message": f"unsupported operation {name!r}"})
        return
    try:
        parsed = operation.model(**params)
    except (PydanticValidationError, TypeError, NexusError) as exc:
        message = exc.message if isinstance(exc, NexusError) else str(exc)
        audit.record(uid, pid, name, params, "rejected", "invalid parameters", via=via)
        send({"type": "error", "code": "invalid", "message": f"invalid parameters: {message}"[:500]})
        return
    if operation.action and authorize is not None:
        allowed, how = authorize(operation.action)
        if not allowed:
            audit.record(uid, pid, name, params, "denied", how, via=via)
            send({"type": "error", "code": "unauthorized", "message": f"not authorized: {how}"})
            return
    ctx = ops.Context(emit=send, cancelled=cancelled, uid=uid)
    try:
        data = operation.handler(parsed, ctx)
        audit.record(uid, pid, name, params, "ok", via=via)
        send({"type": "result", "ok": True, "data": data})
    except NexusError as exc:
        code = "invalid" if isinstance(exc, ValidationError) else getattr(exc, "code", "failed")
        message = exc.message + (f" ({exc.hint})" if exc.hint else "")
        audit.record(uid, pid, name, params, "failed", message, via=via)
        send({"type": "error", "code": code if isinstance(code, str) else "failed", "message": message})
    except (ValueError, OSError) as exc:
        audit.record(uid, pid, name, params, "failed", str(exc), via=via)
        send({"type": "error", "code": "failed", "message": f"{exc.__class__.__name__}: {exc}"[:500]})
