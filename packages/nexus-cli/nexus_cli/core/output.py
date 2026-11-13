"""Console helpers shared by command modules."""

from __future__ import annotations

import json
import sys
from typing import Any

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.theme import Theme

from nexus_cli.core.errors import AbortedError

NEXUS_THEME = Theme(
    {
        "accent": "#31C6BD",
        "accent2": "#C47750",
        "muted": "#9EB3B7",
        "ok": "#3DBE7A",
        "warn": "#D9A441",
        "fail": "#D9574F",
    }
)

console = Console(theme=NEXUS_THEME, highlight=False)
err_console = Console(theme=NEXUS_THEME, stderr=True, highlight=False)

STATUS_STYLE = {"ok": "ok", "warn": "warn", "fail": "fail", "skip": "muted", "info": "accent"}
STATUS_ICON = {"ok": "✔", "warn": "!", "fail": "✘", "skip": "–", "info": "•"}


def print_json(data: Any) -> None:
    """Emit JSON on stdout without Rich markup."""
    if isinstance(data, BaseModel):
        payload = data.model_dump(mode="json")
    elif isinstance(data, list):
        payload = [d.model_dump(mode="json") if isinstance(d, BaseModel) else d for d in data]
    else:
        payload = data
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=False) + "\n")


def status_text(status: str) -> str:
    style = STATUS_STYLE.get(status, "muted")
    return f"[{style}]{STATUS_ICON.get(status, '?')} {status.upper()}[/{style}]"


def confirm(question: str, default: bool = False) -> bool:
    """Ask for explicit confirmation. Refuses (raises) when stdin is not a TTY."""
    if not sys.stdin.isatty():
        raise AbortedError(
            "confirmation required but no interactive terminal is attached",
            hint="run the command from an interactive terminal",
        )
    return typer.confirm(question, default=default)
