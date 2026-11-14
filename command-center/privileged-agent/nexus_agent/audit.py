"""Audit log of every privileged request (JSON lines, size-rotated, secrets redacted)."""

from __future__ import annotations

import json
import logging
import os
import pwd
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from nexus_core.redact import redact

DEFAULT_AUDIT_PATH = "/var/log/nexusos/agent-audit.log"
_logger: logging.Logger | None = None
_path: Path | None = None


def _get() -> logging.Logger:
    global _logger, _path
    path = Path(os.environ.get("NEXUSOS_AGENT_AUDIT", DEFAULT_AUDIT_PATH))
    if _logger is None or path != _path:
        _path = path
        _logger = logging.getLogger("nexus.agent.audit")
        for old in list(_logger.handlers):
            _logger.removeHandler(old)
            old.close()
        _logger.propagate = False
        try:
            path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
            handler: logging.Handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=5)
            os.chmod(path, 0o640)
        except OSError:
            handler = logging.StreamHandler()  # stderr: never mixed into the event stream
        handler.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(handler)
        _logger.setLevel(logging.INFO)
    return _logger


def record(uid: int, pid: int, op: str, params: dict, outcome: str, detail: str = "", via: str = "agent") -> None:
    try:
        user = pwd.getpwuid(uid).pw_name
    except KeyError:
        user = str(uid)
    _get().info(
        json.dumps(
            {
                "ts": time.time(),
                "user": user,
                "uid": uid,
                "pid": pid,
                "op": op,
                "params": redact(params),
                "outcome": outcome,
                "via": via,  # agent (socket + polkit) or sudo (nexus-admin)
                "detail": detail[:500],
            }
        )
    )
