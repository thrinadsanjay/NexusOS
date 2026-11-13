"""Application registry and integration contract (validated YAML)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from nexus_core import paths
from nexus_core.errors import NexusError, ValidationError

APP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,40}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")
Status = Literal["available", "experimental", "planned", "unavailable"]


class ConfigField(BaseModel):
    key: str
    description: str = ""
    secret: bool = False
    default: str | None = None
    generate: Literal["none", "password", "token", "hex32"] = "none"
    required: bool = False

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        if not ENV_KEY_RE.match(v):
            raise ValueError(f"invalid config key {v!r}")
        return v


class Port(BaseModel):
    name: str
    host_port: int
    bind: str = "127.0.0.1"

    @model_validator(mode="after")
    def _loopback(self) -> Port:
        if self.bind not in ("127.0.0.1", "::1"):
            raise ValueError("application ports must be published on loopback; use the Gateway for LAN access")
        return self


class Health(BaseModel):
    url: str  # http://127.0.0.1:<port>/<path>
    expect_status: int = 200

    @field_validator("url")
    @classmethod
    def _local(cls, v: str) -> str:
        if not re.match(r"^https?://(127\.0\.0\.1|\[::1\]|localhost):\d{1,5}/[A-Za-z0-9._~/\-]*$", v):
            raise ValueError("health checks must target a loopback URL")
        return v


class GatewayHint(BaseModel):
    suggested_hostname: str
    backend_port: int
    websocket: bool = False
    path_prefix: str = "/"


class Dependencies(BaseModel):
    host_packages: list[str] = Field(default_factory=list)
    host_ports_listening: list[int] = Field(default_factory=list, description="services that must already run")
    applications: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Deployment(BaseModel):
    method: Literal["compose"] = "compose"
    project: str
    source_repo: str | None = None
    source_ref: str | None = None
    build_from_source: bool = False
    upstream_compose: str | None = Field(default=None, description="compose file path inside the source repo")
    files: list[str] = Field(default_factory=list, description="NexusOS deployment files (relative to the app dir)")
    backup_volumes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _pins(self) -> Deployment:
        if self.source_repo:
            if not self.source_repo.startswith("https://github.com/"):
                raise ValueError("source repositories must be https GitHub URLs")
            if not self.source_ref or not SHA_RE.match(self.source_ref):
                raise ValueError("source_ref must pin a full 40-character commit SHA")
        return self


class Contract(BaseModel):
    """What an application declares to integrate with the Command Center."""

    api_endpoint: str | None = None
    health_endpoint: str | None = None
    authentication: Literal["none", "local", "oidc", "keycloak-optional"] = "local"
    navigation: list[dict[str, str]] = Field(default_factory=list)
    embed: Literal["none", "window", "webview"] = "window"
    permissions: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class AppDefinition(BaseModel):
    id: str
    name: str
    version: str
    summary: str
    description: str = ""
    category: str = "Applications"
    status: Status
    status_reason: str = ""
    homepage: str | None = None
    deployment: Deployment | None = None
    config: list[ConfigField] = Field(default_factory=list)
    ports: list[Port] = Field(default_factory=list)
    health: Health | None = None
    gateway: GatewayHint | None = None
    dependencies: Dependencies = Field(default_factory=Dependencies)
    contract: Contract = Field(default_factory=Contract)
    resources: dict[str, str] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not APP_ID_RE.match(v):
            raise ValueError("invalid application id")
        return v

    @model_validator(mode="after")
    def _installable(self) -> AppDefinition:
        if self.status in ("available", "experimental") and self.deployment is None:
            raise ValueError(f"{self.id}: installable applications need a deployment definition")
        if self.status in ("planned", "unavailable") and not self.status_reason:
            raise ValueError(f"{self.id}: explain why the application is {self.status}")
        return self

    @property
    def installable(self) -> bool:
        return self.status in ("available", "experimental")


def registry_dir() -> Path:
    override = os.environ.get("NEXUSOS_APP_REGISTRY")
    if override:
        return Path(override)
    installed = paths.share_dir() / "applications"
    if installed.exists():
        return installed
    return Path(__file__).resolve().parents[4] / "applications"  # repository checkout


def load_registry(root: Path | None = None) -> dict[str, AppDefinition]:
    root = root or registry_dir()
    apps: dict[str, AppDefinition] = {}
    for path in sorted((root / "registry").glob("*.yaml")):
        try:
            app = AppDefinition(**(yaml.safe_load(path.read_text()) or {}))
        except (yaml.YAMLError, ValueError, TypeError) as exc:
            raise ValidationError(f"invalid registry entry {path.name}: {exc}") from exc
        if app.id != path.stem:
            raise ValidationError(f"registry file {path.name} declares id {app.id}")
        if app.deployment:
            for rel in app.deployment.files:
                if not (root / app.id / rel).is_file():
                    raise ValidationError(f"{app.id}: deployment file missing: {rel}")
        apps[app.id] = app
    for app in apps.values():
        for dep in app.dependencies.applications:
            if dep not in apps:
                raise ValidationError(f"{app.id} depends on unknown application {dep}")
    return apps


def get(app_id: str, root: Path | None = None) -> AppDefinition:
    apps = load_registry(root)
    if app_id not in apps:
        raise NexusError(f"unknown application {app_id!r}", hint="list applications with `nexus apps list`")
    return apps[app_id]
