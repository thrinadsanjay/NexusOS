"""Activate gateway configuration safely: render -> stage -> swap -> ``nginx -t`` -> reload.

* Generated configuration is kept apart from the source route definitions.
* The previous working configuration is backed up before every activation.
* NGINX is never reloaded when ``nginx -t`` fails; the previous tree is restored.
* A failed reload restores the previous tree and reloads it again.

Runs inside the privileged agent (it writes /etc/nexusos/gateway and reloads NGINX),
but every path and command is injectable so it is fully testable unprivileged.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from nexus_core import runner
from nexus_core.errors import NexusError, ValidationError
from nexus_core.gateway.model import Route, find_conflicts, load_routes
from nexus_core.gateway.render import cert_paths, render_all

KEEP_BACKUPS = 10


@dataclass
class GatewayEnv:
    gateway_dir: Path
    nginx_test: Sequence[str] = ("nginx", "-t", "-q")
    nginx_reload: Sequence[str] = ("systemctl", "reload", "nginx")
    check_backends: bool = True

    @property
    def routes_dir(self) -> Path:
        return self.gateway_dir / "routes"

    @property
    def generated(self) -> Path:
        return self.gateway_dir / "generated"


@dataclass
class ApplyResult:
    ok: bool
    applied: list[str] = field(default_factory=list)
    message: str = ""
    nginx_output: str = ""
    rolled_back: bool = False
    backup: str | None = None


def ensure_layout(env: GatewayEnv) -> None:
    for sub, mode in (
        ("routes", 0o755),
        ("generated", 0o755),
        ("backups", 0o700),
        ("certificates", 0o755),
        ("acme", 0o755),
        ("ca", 0o700),
    ):
        (env.gateway_dir / sub).mkdir(mode=mode, parents=True, exist_ok=True)


def validate(env: GatewayEnv, routes: list[Route]) -> list[str]:
    problems = find_conflicts(routes)
    for r in routes:
        if not (r.enabled and r.approved):
            continue
        if env.check_backends:
            try:
                r.check_backend()
            except ValidationError as exc:
                problems.append(f"{r.id}: {exc.message}")
        if r.tls != "none":
            cert, key = cert_paths(r, env.gateway_dir)
            if not cert.exists() or not key.exists():
                problems.append(f"{r.id}: certificate files missing ({cert.parent}); issue or import one first")
    return problems


def _write_tree(target: Path, files: dict[str, str]) -> None:
    target.mkdir(mode=0o755, parents=True)
    for name, content in files.items():
        (target / name).write_text(content, encoding="utf-8")
        os.chmod(target / name, 0o644)


def _backup(env: GatewayEnv) -> Path | None:
    if not env.generated.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() % 1_000_000:06d}"
    dest = env.gateway_dir / "backups" / stamp
    shutil.copytree(env.generated, dest)
    backups = sorted((env.gateway_dir / "backups").iterdir())
    for old in backups[:-KEEP_BACKUPS]:
        shutil.rmtree(old, ignore_errors=True)
    return dest


def _swap_in(env: GatewayEnv, new_tree: Path) -> Path:
    previous = env.gateway_dir / "generated.prev"
    if previous.exists():
        shutil.rmtree(previous)
    if env.generated.exists():
        env.generated.rename(previous)
    new_tree.rename(env.generated)
    return previous


def _restore(env: GatewayEnv, previous: Path) -> None:
    if env.generated.exists():
        shutil.rmtree(env.generated)
    if previous.exists():
        previous.rename(env.generated)
    else:
        env.generated.mkdir(mode=0o755)


def _test_and_reload(env: GatewayEnv) -> tuple[bool, str, bool]:
    test = runner.run(list(env.nginx_test), timeout=30, env=runner.safe_env())
    output = (test.stdout + test.stderr).strip()
    if not test.ok:
        return False, output, False
    reload = runner.run(list(env.nginx_reload), timeout=60, env=runner.safe_env())
    if not reload.ok:
        return False, (output + "\n" + reload.stderr).strip(), True
    return True, output, True


def apply(env: GatewayEnv) -> ApplyResult:
    ensure_layout(env)
    routes = load_routes(env.routes_dir)
    problems = validate(env, routes)
    if problems:
        return ApplyResult(ok=False, message="validation failed: " + "; ".join(problems))
    files = render_all(routes, env.gateway_dir)
    staging = env.gateway_dir / "generated.staging"
    if staging.exists():
        shutil.rmtree(staging)
    _write_tree(staging, files)
    backup = _backup(env)
    previous = _swap_in(env, staging)
    ok, output, reloaded = _test_and_reload(env)
    if not ok:
        _restore(env, previous)
        if reloaded:  # reload failed after a passing test: reload the restored config
            runner.run(list(env.nginx_reload), timeout=60, env=runner.safe_env())
        return ApplyResult(
            ok=False,
            message="nginx rejected the new configuration; previous configuration restored",
            nginx_output=output,
            rolled_back=True,
            backup=str(backup) if backup else None,
        )
    if previous.exists():
        shutil.rmtree(previous)
    digest = hashlib.sha256("".join(sorted(files.values())).encode()).hexdigest()
    (env.gateway_dir / "state.json").write_text(
        json.dumps({"applied_at": time.time(), "routes": sorted(files), "sha256": digest}, indent=2)
    )
    return ApplyResult(
        ok=True,
        applied=sorted(files),
        message=f"{len(files)} route(s) active",
        nginx_output=output,
        backup=str(backup) if backup else None,
    )


def rollback(env: GatewayEnv) -> ApplyResult:
    """Restore the most recent backup (if it passes nginx -t)."""
    backups = sorted((env.gateway_dir / "backups").iterdir()) if (env.gateway_dir / "backups").exists() else []
    if not backups:
        raise NexusError("no gateway backup to roll back to")
    latest = backups[-1]
    staging = env.gateway_dir / "generated.staging"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(latest, staging)
    previous = _swap_in(env, staging)
    ok, output, reloaded = _test_and_reload(env)
    if not ok:
        _restore(env, previous)
        if reloaded:
            runner.run(list(env.nginx_reload), timeout=60, env=runner.safe_env())
        return ApplyResult(
            ok=False,
            message="backup failed nginx -t; current configuration kept",
            nginx_output=output,
            rolled_back=True,
        )
    shutil.rmtree(previous, ignore_errors=True)
    shutil.rmtree(latest, ignore_errors=True)
    return ApplyResult(ok=True, message=f"restored backup {latest.name}", nginx_output=output)
