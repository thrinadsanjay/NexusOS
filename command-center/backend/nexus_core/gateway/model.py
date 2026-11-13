"""Gateway route model and validation (injection and SSRF safe)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from nexus_core import validation
from nexus_core.errors import ValidationError

ROUTE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,40}$")
BODY_SIZE_RE = re.compile(r"^[0-9]{1,5}[kmg]?$")
# Names that can never receive publicly trusted certificates.
NON_PUBLIC_SUFFIXES = (
    ".local",
    ".lan",
    ".internal",
    ".home.arpa",
    ".localhost",
    ".test",
    ".example",
    ".invalid",
    ".localdomain",
    ".home",
    ".corp",
    ".intranet",
)

TlsMode = Literal["none", "self-signed", "internal-ca", "letsencrypt", "imported"]
Access = Literal["localhost", "lan", "public"]


class Route(BaseModel):
    id: str
    hostname: str
    path_prefix: str = "/"
    backend_scheme: Literal["http", "https"] = "http"
    backend_host: str = "127.0.0.1"
    backend_port: int
    tls: TlsMode = "none"
    certificate: str | None = Field(default=None, description="certificate name for internal-ca/self-signed/imported")
    redirect_http: bool = True
    websocket: bool = False
    access: Access = "lan"
    allow_public_backend: bool = False
    max_body_size: str = "64m"
    app_id: str | None = None
    approved: bool = False
    enabled: bool = True
    description: str = ""

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not ROUTE_ID_RE.match(v):
            raise ValueError("route id must be 2-41 chars of a-z, 0-9, '-'")
        return v

    @field_validator("hostname")
    @classmethod
    def _host(cls, v: str) -> str:
        return validation.hostname(v)

    @field_validator("path_prefix")
    @classmethod
    def _path(cls, v: str) -> str:
        return validation.url_path(v)

    @field_validator("backend_host")
    @classmethod
    def _backend(cls, v: str) -> str:
        return validation.host_or_ip(v)

    @field_validator("backend_port")
    @classmethod
    def _port(cls, v: int) -> int:
        return validation.port(v)

    @field_validator("max_body_size")
    @classmethod
    def _body(cls, v: str) -> str:
        if not BODY_SIZE_RE.match(v):
            raise ValueError("max_body_size like 64m, 1g or 512k")
        return v

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str) -> str:
        return validation.single_line(v, max_len=200, field="description").replace("#", "")

    @field_validator("certificate", "app_id")
    @classmethod
    def _names(cls, v: str | None) -> str | None:
        if v is not None and not ROUTE_ID_RE.match(v) and not validation.HOST_LABEL_RE.match(v.replace(".", "-")):
            raise ValueError("invalid name")
        return v

    @model_validator(mode="after")
    def _consistency(self) -> Route:
        if self.tls == "letsencrypt" and is_non_public_name(self.hostname):
            raise ValueError(
                f"{self.hostname} is not a public DNS name; Let's Encrypt cannot issue for it "
                "(use internal-ca or self-signed)"
            )
        if self.tls == "letsencrypt" and self.access != "public":
            # HTTP-01 validation must reach the ACME location from the internet.
            pass
        if self.tls in ("imported",) and not self.certificate:
            raise ValueError("imported TLS requires a certificate name")
        return self

    @property
    def cert_name(self) -> str:
        return self.certificate or self.hostname

    def check_backend(self) -> list[str]:
        """SSRF check of the backend (resolves DNS). Raises ValidationError."""
        return validation.backend_destination(self.backend_host, allow_public=self.allow_public_backend)


def is_non_public_name(hostname: str) -> bool:
    host = hostname.lower()
    return "." not in host or host.endswith(NON_PUBLIC_SUFFIXES)


def load_route(path: Path) -> Route:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return Route(**data)
    except (yaml.YAMLError, TypeError, ValueError) as exc:
        raise ValidationError(f"invalid route file {path.name}: {exc}") from exc


def load_routes(routes_dir: Path) -> list[Route]:
    routes = []
    for path in sorted(routes_dir.glob("*.yaml")) if routes_dir.exists() else []:
        route = load_route(path)
        if route.id != path.stem:
            raise ValidationError(f"route id {route.id} does not match its file name {path.name}")
        routes.append(route)
    return routes


def dump_route(route: Route) -> str:
    return (
        "# NexusOS Gateway route (source definition). Managed by the Command Center / `nexus gateway`.\n"
        + yaml.safe_dump(route.model_dump(), sort_keys=False)
    )


def find_conflicts(routes: list[Route]) -> list[str]:
    seen: dict[tuple[str, str], str] = {}
    problems = []
    for r in routes:
        if not (r.enabled and r.approved):
            continue
        key = (r.hostname, r.path_prefix)
        if key in seen:
            problems.append(f"routes {seen[key]} and {r.id} both serve {r.hostname}{r.path_prefix}")
        seen[key] = r.id
    return problems
