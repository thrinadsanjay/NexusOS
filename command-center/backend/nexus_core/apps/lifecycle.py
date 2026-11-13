"""Application lifecycle on Docker Compose: install, start/stop/restart, update, status,
health, logs, backup/restore and uninstall. Each application is a separate compose
project (``nexus-<id>``) with its own state directory and generated secrets."""

from __future__ import annotations

import json
import secrets
import shutil
import socket
import tarfile
import time
from pathlib import Path

import httpx
from pydantic import BaseModel

from nexus_core import compose, paths, runner
from nexus_core.apps.registry import AppDefinition, get, load_registry, registry_dir
from nexus_core.errors import DependencyMissingError, NexusError, ValidationError

BACKUP_IMAGE = "busybox:1.37"


class AppState(BaseModel):
    id: str
    installed: bool
    version: str | None = None
    status: str = "not-installed"
    services: list[dict] = []
    health: str | None = None
    urls: list[str] = []


def _deployment(app: AppDefinition):
    if app.deployment is None:
        raise NexusError(f"{app.name} has no deployment definition ({app.status})")
    return app.deployment


def app_dir(app_id: str) -> Path:
    return paths.data_dir() / "apps" / app_id


def _state_file(app_id: str) -> Path:
    return app_dir(app_id) / "nexus-app.json"


def installed_ids() -> list[str]:
    base = paths.data_dir() / "apps"
    return sorted(p.name for p in base.iterdir() if (p / "nexus-app.json").exists()) if base.exists() else []


def compose_files(app: AppDefinition) -> list[Path]:
    d = app_dir(app.id)
    files = []
    if app.deployment and app.deployment.upstream_compose:
        files.append(d / "src" / app.deployment.upstream_compose)
    files += [
        d / Path(f).name for f in (app.deployment.files if app.deployment else []) if f.endswith((".yaml", ".yml"))
    ]
    return files


def _port_listening(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def check_dependencies(app: AppDefinition) -> list[str]:
    problems = []
    if not app.installable:
        problems.append(f"{app.name} is {app.status}: {app.status_reason}")
    if runner.which("docker") is None:
        problems.append("Docker Engine is not installed (Development Workstation or Private Cloud Host profile)")
    elif not runner.run(["docker", "compose", "version"], timeout=10).ok:
        problems.append("Docker Compose plugin missing (docker-compose-v2)")
    if app.deployment and app.deployment.source_repo and runner.which("git") is None:
        problems.append("git is required to fetch the application source")
    for port in app.dependencies.host_ports_listening:
        if not _port_listening(port):
            problems.append(f"required host service on port {port} is not listening")
    for port in app.ports:
        if _port_listening(port.host_port) and app.id not in installed_ids():
            problems.append(f"port {port.host_port} ({port.name}) is already in use")
    for dep in app.dependencies.applications:
        if dep not in installed_ids():
            problems.append(f"requires application {dep}")
    return problems


def _generate(kind: str) -> str:
    if kind == "password":
        return secrets.token_urlsafe(18)
    if kind == "hex32":
        return secrets.token_hex(32)
    return secrets.token_urlsafe(32)


def build_env(
    app: AppDefinition, overrides: dict[str, str] | None = None, existing: dict[str, str] | None = None
) -> dict[str, str]:
    overrides = overrides or {}
    existing = existing or {}
    env: dict[str, str] = {}
    for field in app.config:
        if field.key in overrides:
            env[field.key] = overrides[field.key]
        elif field.key in existing:
            env[field.key] = existing[field.key]  # keep secrets stable across updates
        elif field.generate != "none":
            env[field.key] = _generate(field.generate)
        elif field.default is not None:
            env[field.key] = field.default
        elif field.required:
            raise ValidationError(f"{app.id}: configuration value {field.key} is required")
    unknown = set(overrides) - {f.key for f in app.config}
    if unknown:
        raise ValidationError(f"unknown configuration keys: {', '.join(sorted(unknown))}")
    return env


def _read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


def _fetch_source(app: AppDefinition, target: Path) -> None:
    dep = _deployment(app)
    if not dep.source_repo or not dep.source_ref:
        raise NexusError(f"{app.name} has no pinned source repository")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    steps = [
        ["git", "init", "-q", str(target)],
        ["git", "-C", str(target), "fetch", "-q", "--depth", "1", dep.source_repo, dep.source_ref],
        ["git", "-C", str(target), "checkout", "-q", "FETCH_HEAD"],
    ]
    for cmd in steps:
        result = runner.run(cmd, timeout=600)
        if not result.ok:
            raise NexusError(f"fetching {app.name} source failed", hint=runner.first_line(result.stderr))


def install(app_id: str, config: dict[str, str] | None = None, root: Path | None = None) -> AppState:
    app = get(app_id, root)
    problems = check_dependencies(app)
    if problems:
        raise DependencyMissingError(f"cannot install {app.name}", hint="; ".join(problems))
    _deployment(app)
    d = app_dir(app.id)
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    reg = root or registry_dir()
    for rel in app.deployment.files:
        shutil.copyfile(reg / app.id / rel, d / Path(rel).name)
    if app.deployment.source_repo:
        _fetch_source(app, d / "src")
    env_path = d / ".env"
    compose.write_env_file(env_path, build_env(app, config, _read_env(env_path)))
    files = compose_files(app)
    ok, message = compose.validate(app.deployment.project, files, env_path)
    if not ok:
        raise NexusError(f"{app.name} deployment definition is invalid", hint=message)
    compose.run_action(
        app.deployment.project, files, "up-build" if app.deployment.build_from_source else "up", env_path
    )
    _state_file(app.id).write_text(
        json.dumps(
            {"id": app.id, "version": app.version, "installed_at": time.time(), "source_ref": app.deployment.source_ref}
        )
    )
    return status(app.id, root)


def _require_installed(app_id: str, root: Path | None) -> AppDefinition:
    app = get(app_id, root)
    if app_id not in installed_ids():
        raise NexusError(f"{app.name} is not installed", hint=f"nexus apps install {app_id}")
    return app


def action(app_id: str, verb: str, root: Path | None = None) -> None:
    app = _require_installed(app_id, root)
    if verb not in ("start", "stop", "restart"):
        raise ValidationError(f"unsupported action {verb!r}")
    _deployment(app)
    compose.run_action(app.deployment.project, compose_files(app), verb, app_dir(app.id) / ".env")


def update(app_id: str, root: Path | None = None) -> AppState:
    """Re-deploy at the version pinned in the current registry (pull images / rebuild at new ref)."""
    app = _require_installed(app_id, root)
    _deployment(app)
    d = app_dir(app.id)
    reg = root or registry_dir()
    for rel in app.deployment.files:
        shutil.copyfile(reg / app.id / rel, d / Path(rel).name)
    state = json.loads(_state_file(app.id).read_text())
    if app.deployment.source_repo and state.get("source_ref") != app.deployment.source_ref:
        _fetch_source(app, d / "src")
    env_path = d / ".env"
    compose.write_env_file(env_path, build_env(app, None, _read_env(env_path)))
    if not app.deployment.build_from_source:
        compose.run_action(app.deployment.project, compose_files(app), "pull", env_path)
    compose.run_action(
        app.deployment.project, compose_files(app), "up-build" if app.deployment.build_from_source else "up", env_path
    )
    state.update(version=app.version, source_ref=app.deployment.source_ref, updated_at=time.time())
    _state_file(app.id).write_text(json.dumps(state))
    return status(app.id, root)


def uninstall(app_id: str, delete_data: bool = False, root: Path | None = None) -> None:
    app = _require_installed(app_id, root)
    _deployment(app)
    compose.run_action(
        app.deployment.project, compose_files(app), "down-volumes" if delete_data else "down", app_dir(app.id) / ".env"
    )
    if delete_data:
        shutil.rmtree(app_dir(app.id))
    else:
        _state_file(app.id).unlink()


def health(app: AppDefinition, transport: httpx.BaseTransport | None = None) -> str:
    if not app.health:
        return "unknown"
    try:
        with httpx.Client(timeout=3, transport=transport) as client:
            response = client.get(app.health.url)
        return "healthy" if response.status_code == app.health.expect_status else f"unhealthy ({response.status_code})"
    except httpx.HTTPError:
        return "unreachable"


def status(app_id: str, root: Path | None = None) -> AppState:
    app = get(app_id, root)
    if app_id not in installed_ids():
        return AppState(id=app_id, installed=False)
    state = json.loads(_state_file(app_id).read_text())
    _deployment(app)
    try:
        svc = compose.ps(app.deployment.project, compose_files(app), app_dir(app_id) / ".env")
    except (NexusError, ValidationError):
        svc = []
    running = sum(1 for s in svc if s.get("State") == "running")
    overall = "running" if svc and running == len(svc) else ("partial" if running else "stopped")
    urls = [f"http://127.0.0.1:{p.host_port}" for p in app.ports]
    return AppState(
        id=app_id,
        installed=True,
        version=state.get("version"),
        status=overall,
        services=[{"name": s.get("Service"), "state": s.get("State"), "health": s.get("Health")} for s in svc],
        health=health(app) if running else None,
        urls=urls,
    )


def logs(app_id: str, tail: int = 200, root: Path | None = None) -> str:
    app = _require_installed(app_id, root)
    _deployment(app)
    return compose.logs(app.deployment.project, compose_files(app), app_dir(app_id) / ".env", tail)


def backup(app_id: str, destination: Path, root: Path | None = None) -> Path:
    """Archive the deployment directory (incl. .env, mode 0600 archive) and named volumes."""
    app = _require_installed(app_id, root)
    _deployment(app)
    destination.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    work = destination / f"{app.id}-{stamp}"
    work.mkdir(mode=0o700)
    with tarfile.open(work / "config.tar.gz", "w:gz") as tar:
        for item in app_dir(app.id).iterdir():
            if item.name != "src":
                tar.add(item, arcname=item.name)
    for volume in app.deployment.backup_volumes:
        full = f"{app.deployment.project}_{volume}"
        result = runner.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{full}:/data:ro",
                "-v",
                f"{work}:/backup",
                BACKUP_IMAGE,
                "tar",
                "czf",
                f"/backup/volume-{volume}.tar.gz",
                "-C",
                "/data",
                ".",
            ],
            timeout=3600,
        )
        if not result.ok:
            raise NexusError(f"backup of volume {volume} failed", hint=runner.first_line(result.stderr))
    archive = Path(shutil.make_archive(str(work), "gztar", root_dir=work))
    archive.chmod(0o600)
    shutil.rmtree(work)
    return archive


def restore(app_id: str, archive: Path, *, confirmed: bool, root: Path | None = None) -> None:
    """Restore volumes and configuration from :func:`backup` (stops the app; overwrites data)."""
    if not confirmed:
        raise ValidationError("restore overwrites application data and requires confirmation")
    app = _require_installed(app_id, root)
    _deployment(app)
    action(app_id, "stop", root)
    work = archive.parent / (archive.name + ".restore")
    shutil.unpack_archive(str(archive), str(work), "gztar", filter="data")
    with tarfile.open(work / "config.tar.gz") as tar:
        tar.extractall(app_dir(app.id), filter="data")
    for volume in app.deployment.backup_volumes:
        tarball = work / f"volume-{volume}.tar.gz"
        if tarball.exists():
            full = f"{app.deployment.project}_{volume}"
            runner.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{full}:/data",
                    "-v",
                    f"{work}:/backup:ro",
                    BACKUP_IMAGE,
                    "sh",
                    "-c",
                    f"rm -rf /data/* && tar xzf /backup/volume-{volume}.tar.gz -C /data",
                ],
                timeout=3600,
            )
    shutil.rmtree(work)
    action(app_id, "start", root)


def catalog(root: Path | None = None) -> list[tuple[AppDefinition, AppState]]:
    out = []
    for app in load_registry(root).values():
        installed = app.id in installed_ids()
        out.append((app, status(app.id, root) if installed else AppState(id=app.id, installed=False)))
    return out


def suggested_route(app: AppDefinition) -> dict | None:
    """Gateway route proposal (pending approval) for an installed application."""
    if not app.gateway:
        return None
    return {
        "id": app.id,
        "hostname": app.gateway.suggested_hostname,
        "backend_host": "127.0.0.1",
        "backend_port": app.gateway.backend_port,
        "websocket": app.gateway.websocket,
        "path_prefix": app.gateway.path_prefix,
        "tls": "internal-ca",
        "access": "lan",
        "app_id": app.id,
        "approved": False,
        "description": f"{app.name} (suggested at install)",
    }
