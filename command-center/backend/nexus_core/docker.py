"""Docker Engine detection via its local UNIX socket API (read-only endpoints only)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import httpx

from nexus_core import runner
from nexus_core.log import get_logger
from nexus_core.models import ContainerInfo, DockerStatus

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


# =====================================================================================
# Full Docker Engine client (v0.2) used by the Containers module and `nexus containers`.
# Talks to the local UNIX socket only; never exposes the daemon; output is redacted.
# =====================================================================================

import json as _json  # noqa: E402
from collections.abc import Iterator  # noqa: E402
from typing import Any  # noqa: E402

from nexus_core import validation  # noqa: E402
from nexus_core.errors import DependencyMissingError, NexusError  # noqa: E402
from nexus_core.redact import redact  # noqa: E402

DOCKER_SECURITY_NOTE = (
    "Docker administration is root-equivalent: anyone who can start containers can mount the host "
    "filesystem. NexusOS only talks to the local socket and never exposes the daemon on the network."
)


class DockerClient:
    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 15.0) -> None:
        if transport is None:
            sock, error = resolve_socket()
            if error or sock is None:
                raise DependencyMissingError(error or "Docker socket not found")
            if not sock.exists():
                raise DependencyMissingError(
                    "Docker Engine is not running or not installed",
                    hint="install the Development Workstation profile or start docker.service",
                )
            if not os.access(sock, os.R_OK | os.W_OK):
                raise NexusError("permission denied on the Docker socket", hint=DOCKER_SECURITY_NOTE)
            transport = httpx.HTTPTransport(uds=str(sock))
        self._client = httpx.Client(transport=transport, base_url="http://docker/v1.43", timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DockerClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------- plumbing
    def _req(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise DependencyMissingError(f"Docker Engine API unavailable: {exc.__class__.__name__}") from None
        if response.status_code >= 400:
            try:
                message = response.json().get("message", response.text)
            except ValueError:
                message = response.text
            raise NexusError(f"Docker: {message.strip()[:300]}")
        return response

    def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._req(method, path, **kwargs)
        return response.json() if response.content else None

    # ------------------------------------------------------------- system
    def version(self) -> dict:
        return self._json("GET", "/version")

    def disk_usage(self) -> dict:
        data = self._json("GET", "/system/df")
        return {
            "images": sum(i.get("Size", 0) for i in data.get("Images") or []),
            "containers": sum(c.get("SizeRw", 0) or 0 for c in data.get("Containers") or []),
            "volumes": sum((v.get("UsageData") or {}).get("Size", 0) or 0 for v in data.get("Volumes") or []),
            "build_cache": sum(b.get("Size", 0) for b in data.get("BuildCache") or []),
        }

    # ------------------------------------------------------------- containers
    def containers(self, all_containers: bool = True) -> list[ContainerInfo]:
        return parse_containers(self._json("GET", "/containers/json", params={"all": str(all_containers).lower()}))

    def container_action(self, ident: str, action: str) -> None:
        validation.docker_id(ident)
        allowed = {"start", "stop", "restart", "pause", "unpause", "kill"}
        if action not in allowed:
            raise NexusError(f"unsupported container action {action!r}")
        self._req("POST", f"/containers/{ident}/{action}", timeout=60)

    def remove_container(self, ident: str, force: bool = False, volumes: bool = False) -> None:
        self._req(
            "DELETE",
            f"/containers/{validation.docker_id(ident)}",
            params={"force": str(force).lower(), "v": str(volumes).lower()},
        )

    def inspect_container(self, ident: str) -> dict:
        """Inspection output with environment values and credentials redacted."""
        return redact(self._json("GET", f"/containers/{validation.docker_id(ident)}/json"), redact_all_env=True)

    def logs(self, ident: str, tail: int = 200, timestamps: bool = False) -> str:
        tail = max(1, min(int(tail), 5000))
        raw = self._req(
            "GET",
            f"/containers/{validation.docker_id(ident)}/logs",
            params={"stdout": "true", "stderr": "true", "tail": str(tail), "timestamps": str(timestamps).lower()},
        ).content
        return demux_logs(raw)

    def stats(self, ident: str) -> dict:
        """One-shot resource usage (no streaming, no background polling)."""
        data = self._json("GET", f"/containers/{validation.docker_id(ident)}/stats", params={"stream": "false"})
        cpu = data.get("cpu_stats", {})
        pre = data.get("precpu_stats", {})
        cpu_delta = cpu.get("cpu_usage", {}).get("total_usage", 0) - pre.get("cpu_usage", {}).get("total_usage", 0)
        sys_delta = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
        cpus = cpu.get("online_cpus") or 1
        mem = data.get("memory_stats", {})
        return {
            "cpu_percent": round(100.0 * cpu_delta / sys_delta * cpus, 2) if sys_delta > 0 else 0.0,
            "memory_bytes": mem.get("usage", 0) - (mem.get("stats", {}).get("inactive_file", 0) or 0),
            "memory_limit": mem.get("limit", 0),
        }

    # ------------------------------------------------------------- images
    def images(self) -> list[dict]:
        out = []
        for img in self._json("GET", "/images/json"):
            out.append(
                {
                    "id": img["Id"].split(":")[-1][:12],
                    "tags": img.get("RepoTags") or ["<none>"],
                    "size": img.get("Size", 0),
                    "created": img.get("Created", 0),
                }
            )
        return out

    def pull(self, reference: str) -> Iterator[dict]:
        validation.docker_ref(reference)
        image, _, tag = reference.rpartition(":") if ":" in reference.split("/")[-1] else (reference, "", "latest")
        with self._client.stream(
            "POST", "/images/create", params={"fromImage": image or reference, "tag": tag}, timeout=None
        ) as response:
            if response.status_code >= 400:
                raise NexusError(f"Docker pull failed: HTTP {response.status_code}")
            for line in response.iter_lines():
                if line.strip():
                    event = _json.loads(line)
                    if "error" in event:
                        raise NexusError(f"Docker pull failed: {event['error']}")
                    yield event

    def remove_image(self, ident: str, force: bool = False) -> None:
        self._req("DELETE", f"/images/{validation.docker_ref(ident)}", params={"force": str(force).lower()})

    def inspect_image(self, ident: str) -> dict:
        return redact(self._json("GET", f"/images/{validation.docker_ref(ident)}/json"), redact_all_env=True)

    def tag_image(self, ident: str, repo: str, tag: str) -> None:
        validation.docker_ref(f"{repo}:{tag}")
        self._req("POST", f"/images/{validation.docker_ref(ident)}/tag", params={"repo": repo, "tag": tag})

    def search(self, term: str, limit: int = 25) -> list[dict]:
        term = validation.single_line(term, max_len=100)
        return self._json("GET", "/images/search", params={"term": term, "limit": str(limit)}, timeout=30)

    # ------------------------------------------------------------- volumes
    def volumes(self) -> list[dict]:
        data = self._json("GET", "/volumes") or {}
        return [
            {
                "name": v["Name"],
                "driver": v.get("Driver"),
                "mountpoint": v.get("Mountpoint"),
                "labels": v.get("Labels") or {},
            }
            for v in data.get("Volumes") or []
        ]

    def create_volume(self, name: str) -> None:
        self._req("POST", "/volumes/create", json={"Name": validation.docker_id(name)})

    def remove_volume(self, name: str) -> None:
        self._req("DELETE", f"/volumes/{validation.docker_id(name)}")

    def prune_volumes(self) -> dict:
        return self._json("POST", "/volumes/prune")

    # ------------------------------------------------------------- networks
    def networks(self) -> list[dict]:
        return [
            {
                "id": n["Id"][:12],
                "name": n["Name"],
                "driver": n.get("Driver"),
                "scope": n.get("Scope"),
                "internal": n.get("Internal", False),
            }
            for n in self._json("GET", "/networks")
        ]

    def create_network(self, name: str, internal: bool = False) -> None:
        self._req("POST", "/networks/create", json={"Name": validation.docker_id(name), "Internal": internal})

    def inspect_network(self, ident: str) -> dict:
        return redact(self._json("GET", f"/networks/{validation.docker_id(ident)}"))

    def connect(self, network: str, container: str) -> None:
        self._req(
            "POST",
            f"/networks/{validation.docker_id(network)}/connect",
            json={"Container": validation.docker_id(container)},
        )

    def disconnect(self, network: str, container: str) -> None:
        self._req(
            "POST",
            f"/networks/{validation.docker_id(network)}/disconnect",
            json={"Container": validation.docker_id(container)},
        )

    def remove_network(self, ident: str) -> None:
        self._req("DELETE", f"/networks/{validation.docker_id(ident)}")

    def prune_networks(self) -> dict:
        return self._json("POST", "/networks/prune")

    # ------------------------------------------------------------- compose discovery
    def compose_projects(self) -> list[dict]:
        projects: dict[str, dict] = {}
        for item in self._json("GET", "/containers/json", params={"all": "true"}):
            labels = item.get("Labels") or {}
            name = labels.get("com.docker.compose.project")
            if not name:
                continue
            proj = projects.setdefault(
                name,
                {
                    "name": name,
                    "working_dir": labels.get("com.docker.compose.project.working_dir"),
                    "config_files": labels.get("com.docker.compose.project.config_files"),
                    "services": {},
                    "running": 0,
                    "total": 0,
                },
            )
            proj["services"][labels.get("com.docker.compose.service", "?")] = item.get("State")
            proj["total"] += 1
            proj["running"] += item.get("State") == "running"
        return sorted(projects.values(), key=lambda p: p["name"])


def demux_logs(raw: bytes) -> str:
    """Decode Docker's multiplexed log stream (8-byte frame headers) or plain TTY output."""
    out, i = [], 0
    if len(raw) >= 8 and raw[0] in (0, 1, 2) and raw[1:4] == b"\x00\x00\x00":
        while i + 8 <= len(raw):
            size = int.from_bytes(raw[i + 4 : i + 8], "big")
            out.append(raw[i + 8 : i + 8 + size])
            i += 8 + size
        data = b"".join(out)
    else:
        data = raw
    from nexus_core.redact import redact_text

    return redact_text(data.decode("utf-8", "replace"))
