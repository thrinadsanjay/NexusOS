"""Docker Engine detection via its local UNIX socket API (read-only endpoints only)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import httpx

from nexus_cli.core import runner
from nexus_cli.core.logging import get_logger
from nexus_cli.models import ContainerInfo, DockerStatus

log = get_logger("docker")

DEFAULT_SOCKET = Path("/var/run/docker.sock")
API_TIMEOUT = 5.0


def resolve_socket() -> tuple[Path | None, str | None]:
    """Return (socket path, error). Honours unix:// DOCKER_HOST and rootless Docker."""
    docker_host = os.environ.get("DOCKER_HOST", "").strip()
    if docker_host:
        if docker_host.startswith("unix://"):
            return Path(docker_host[len("unix://") :]), None
        return None, "DOCKER_HOST uses a non-UNIX transport, which nexus does not query"
    if DEFAULT_SOCKET.exists():
        return DEFAULT_SOCKET, None
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        rootless = Path(runtime_dir) / "docker.sock"
        if rootless.exists():
            return rootless, None
    return DEFAULT_SOCKET, None


def _format_ports(ports: list[dict]) -> list[str]:
    formatted = []
    for port in ports or []:
        private = f"{port.get('PrivatePort')}/{port.get('Type', 'tcp')}"
        if port.get("PublicPort"):
            formatted.append(f"{port.get('IP', '')}:{port['PublicPort']}->{private}".lstrip(":"))
        else:
            formatted.append(private)
    return sorted(set(formatted))


def parse_containers(payload: list[dict]) -> list[ContainerInfo]:
    containers = []
    for item in payload:
        names = item.get("Names") or ["?"]
        containers.append(
            ContainerInfo(
                id=str(item.get("Id", ""))[:12],
                name=names[0].lstrip("/"),
                image=str(item.get("Image", "")),
                state=str(item.get("State", "unknown")),
                status=str(item.get("Status", "")),
                ports=_format_ports(item.get("Ports", [])),
            )
        )
    return containers


def docker_status(include_containers: bool = True, transport: httpx.BaseTransport | None = None) -> DockerStatus:
    cli_installed = runner.which("docker") is not None
    sock, error = resolve_socket()
    status = DockerStatus(cli_installed=cli_installed, socket_path=str(sock or ""), reachable=False)
    if error:
        status.error = error
        return status

    if transport is None:
        if sock is None:
            status.error = "Docker socket could not be determined"
            return status
        if not sock.exists():
            status.error = "Docker Engine socket not found"
            status.hint = (
                "install Docker Engine (see manifests/infrastructure.yaml) and start it: `sudo systemctl start docker`"
                if not cli_installed
                else "start the daemon: `sudo systemctl start docker`"
            )
            return status
        try:
            if not stat.S_ISSOCK(sock.stat().st_mode):
                status.error = f"{sock} is not a socket"
                return status
        except OSError as exc:
            status.error = str(exc)
            return status
        if not os.access(sock, os.R_OK | os.W_OK):
            status.error = "permission denied on the Docker socket"
            status.hint = (
                "membership of the `docker` group grants root-equivalent access; "
                "prefer `sudo docker ...` or rootless Docker (see docs/security.md)"
            )
            return status
        transport = httpx.HTTPTransport(uds=str(sock))

    try:
        with httpx.Client(transport=transport, base_url="http://docker", timeout=API_TIMEOUT) as client:
            version = client.get("/version")
            version.raise_for_status()
            status.server_version = version.json().get("Version")
            status.reachable = True
            if include_containers:
                response = client.get("/containers/json", params={"all": "true"})
                response.raise_for_status()
                status.containers = parse_containers(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        log.debug("docker API error: %s", exc)
        status.error = f"Docker Engine API unavailable: {exc.__class__.__name__}"
        status.hint = "check `systemctl status docker`"
    return status
