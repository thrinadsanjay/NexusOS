"""Secret redaction for diagnostics, logs and inspection output."""

from __future__ import annotations

import re
from typing import Any

REDACTED = "***redacted***"
SENSITIVE_KEY = re.compile(
    r"(pass(word|wd|phrase)?|secret|token|api[_-]?key|private[_-]?key|credential|auth|cookie|session)", re.I
)
_TEXT_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), REDACTED),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + REDACTED),
    (
        re.compile(
            r"(?i)\b([A-Za-z0-9_]*(?:pass(?:word|wd)?|secret|token|api[_-]?key)[A-Za-z0-9_]*)\s*([=:])\s*(\"[^\"]*\"|'[^']*'|\S+)"
        ),
        r"\1\2" + REDACTED,
    ),
    (re.compile(r"(?i)(://[^:/@\s]+:)[^@\s]+@"), r"\1" + REDACTED + "@"),
]


def redact_text(text: str) -> str:
    for pattern, repl in _TEXT_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def _redact_env_entry(entry: str) -> str:
    key, sep, _value = entry.partition("=")
    return f"{key}={REDACTED}" if sep and SENSITIVE_KEY.search(key) else entry


def redact(obj: Any, *, redact_all_env: bool = False) -> Any:
    """Recursively redact sensitive values in dicts/lists (e.g. ``docker inspect`` output)."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if key in {"Env", "env", "environment"} and isinstance(value, list):
                out[key] = [
                    (f"{e.partition('=')[0]}={REDACTED}" if redact_all_env else _redact_env_entry(e))
                    if isinstance(e, str)
                    else e
                    for e in value
                ]
            elif isinstance(key, str) and SENSITIVE_KEY.search(key) and isinstance(value, (str, int, float)):
                out[key] = REDACTED
            else:
                out[key] = redact(value, redact_all_env=redact_all_env)
        return out
    if isinstance(obj, list):
        return [redact(v, redact_all_env=redact_all_env) for v in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj
