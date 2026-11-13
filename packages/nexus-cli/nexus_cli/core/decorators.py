"""Command decorators."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import ParamSpec, TypeVar

import typer

from nexus_cli.core.errors import NexusError
from nexus_cli.core.output import err_console

P = ParamSpec("P")
R = TypeVar("R")


def handle_errors(func: Callable[P, R]) -> Callable[P, R]:
    """Render :class:`NexusError` as a concise message and exit with its code."""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except NexusError as exc:
            err_console.print(f"[fail]error:[/fail] {exc.message}")
            if exc.hint:
                err_console.print(f"[muted]hint:[/muted] {exc.hint}")
            raise typer.Exit(exc.exit_code) from None

    return wrapper
