"""Safe execution of external programs.

All commands are executed as argument lists (``shell=False``) with a timeout.
Failures are converted into :class:`CommandResult` objects instead of exceptions
so callers can degrade gracefully when a dependency is missing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from nexus_core.log import get_logger

log = get_logger("runner")

DEFAULT_TIMEOUT = 15.0

# A minimal, predictable environment for child processes. Secrets present in the
# caller's environment (tokens, cloud credentials) are not forwarded.
_SAFE_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "TERM", "XDG_RUNTIME_DIR", "DOCKER_HOST", "USER")


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    found: bool = True
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.found and not self.timed_out and self.returncode == 0


def which(program: str) -> str | None:
    return shutil.which(program)


def safe_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: os.environ[k] for k in _SAFE_ENV_KEYS if k in os.environ}
    env.setdefault("LC_ALL", "C.UTF-8")
    if extra:
        env.update(extra)
    return env


def run(args: Sequence[str], timeout: float = DEFAULT_TIMEOUT, env: dict[str, str] | None = None) -> CommandResult:
    """Run *args* and capture output. Never raises for missing programs or timeouts."""
    argv = tuple(args)
    if not argv:
        raise ValueError("empty command")
    if which(argv[0]) is None:
        log.debug("program not found: %s", argv[0])
        return CommandResult(argv, 127, "", f"{argv[0]}: not found", found=False)
    log.debug("run: %s", " ".join(argv))
    try:
        proc = subprocess.run(  # noqa: S603 — argv list, shell=False; callers pass validated arguments
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env if env is not None else safe_env(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        log.warning("command timed out after %ss: %s", timeout, argv[0])
        return CommandResult(argv, 124, "", "timed out", timed_out=True)
    except OSError as exc:
        log.debug("cannot execute %s: %s", argv[0], exc)
        return CommandResult(argv, 126, "", str(exc), found=False)
    return CommandResult(argv, proc.returncode, proc.stdout, proc.stderr)


def run_interactive(args: Sequence[str], cwd: Path | None = None) -> int:
    """Run a command attached to the user's terminal (used only after explicit confirmation)."""
    argv = list(args)
    if which(argv[0]) is None:
        return 127
    log.debug("run interactive: %s (cwd=%s)", " ".join(argv), cwd)
    return subprocess.call(argv, cwd=cwd)  # noqa: S603 — CLI-only interactive runner, argv list


def first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""
