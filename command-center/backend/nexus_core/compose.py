"""Docker Compose project management through the official ``docker compose`` plugin.

Projects are identified by name and compose files; commands are argv lists with
validated inputs. Environment files are created with mode 0600 and never printed.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from nexus_core import runner
from nexus_core.errors import DependencyMissingError, NexusError, ValidationError
from nexus_core.redact import redact_text

PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,62}$")


def require_compose() -> None:
    if runner.which("docker") is None:
        raise DependencyMissingError("docker CLI not found", hint="install docker.io and docker-compose-v2")
    if not runner.run(["docker", "compose", "version"], timeout=10).ok:
        raise DependencyMissingError("Docker Compose plugin not found", hint="sudo apt install docker-compose-v2")


def _base(project: str, files: list[Path], env_file: Path | None = None) -> list[str]:
    if not PROJECT_RE.match(project):
        raise ValidationError(f"invalid compose project name {project!r}")
    argv = ["docker", "compose", "-p", project]
    for f in files:
        if not f.is_file():
            raise ValidationError(f"compose file not found: {f}")
        argv += ["-f", str(f)]
    if env_file is not None:
        argv += ["--env-file", str(env_file)]
    return argv


def validate(project: str, files: list[Path], env_file: Path | None = None) -> tuple[bool, str]:
    require_compose()
    result = runner.run([*_base(project, files, env_file), "config", "--quiet"], timeout=60)
    return result.ok, redact_text(result.stderr.strip())


def services(project: str, files: list[Path], env_file: Path | None = None) -> list[str]:
    result = runner.run([*_base(project, files, env_file), "config", "--services"], timeout=60)
    return result.stdout.split() if result.ok else []


def ps(project: str, files: list[Path], env_file: Path | None = None) -> list[dict]:
    result = runner.run([*_base(project, files, env_file), "ps", "--all", "--format", "json"], timeout=60)
    if not result.ok:
        return []
    text = result.stdout.strip()
    if not text:
        return []
    if text.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


ACTIONS = {
    "up": ["up", "-d", "--remove-orphans"],
    "up-build": ["up", "-d", "--build", "--remove-orphans"],
    "start": ["start"],
    "stop": ["stop"],
    "restart": ["restart"],
    "down": ["down"],
    "down-volumes": ["down", "--volumes"],
    "pull": ["pull"],
}


def run_action(
    project: str, files: list[Path], action: str, env_file: Path | None = None, timeout: float = 1800
) -> runner.CommandResult:
    require_compose()
    if action not in ACTIONS:
        raise ValidationError(f"unsupported compose action {action!r}")
    workdir_env = runner.safe_env()
    result = runner.run([*_base(project, files, env_file), *ACTIONS[action]], timeout=timeout, env=workdir_env)
    if not result.ok:
        raise NexusError(
            f"docker compose {action} failed", hint=redact_text(runner.first_line(result.stderr[-2000:]) or "")
        )
    return result


def logs(project: str, files: list[Path], env_file: Path | None = None, tail: int = 200) -> str:
    result = runner.run(
        [*_base(project, files, env_file), "logs", "--no-color", "--tail", str(max(1, min(tail, 5000)))], timeout=60
    )
    return redact_text(result.stdout + result.stderr)


def write_env_file(path: Path, values: dict[str, str]) -> None:
    """Write a compose .env with mode 0600 (contains generated secrets)."""
    for key, value in values.items():
        if not re.match(r"^[A-Z_][A-Z0-9_]{0,63}$", key) or "\n" in str(value):
            raise ValidationError(f"invalid environment entry {key!r}")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")
