"""Pydantic models for structured command output (also used for ``--json``)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["ok", "warn", "fail", "skip", "info"]


class OSRelease(BaseModel):
    name: str = "Linux"
    pretty_name: str = "Linux"
    id: str = "linux"
    id_like: str | None = None
    version_id: str | None = None
    version: str | None = None
    codename: str | None = None
    build_id: str | None = None
    variant: str | None = None

    @property
    def is_nexusos(self) -> bool:
        return self.id == "nexusos"


class VersionInfo(BaseModel):
    cli_version: str
    python_version: str
    os: OSRelease
    nexusos_build: str | None = None
    creator: str | None = None


class MemoryInfo(BaseModel):
    total_bytes: int
    available_bytes: int

    @property
    def used_percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return round(100.0 * (self.total_bytes - self.available_bytes) / self.total_bytes, 1)


class DiskInfo(BaseModel):
    mount: str
    total_bytes: int
    free_bytes: int

    @property
    def used_percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return round(100.0 * (self.total_bytes - self.free_bytes) / self.total_bytes, 1)


class SystemInfo(BaseModel):
    hostname: str
    os: OSRelease
    kernel: str
    architecture: str
    cpu_model: str
    cpu_count: int
    memory: MemoryInfo | None
    disks: list[DiskInfo] = Field(default_factory=list)
    uptime_seconds: float | None = None
    load_average: tuple[float, float, float] | None = None
    desktop_session: str | None = None
    session_type: str | None = None
    virtualization: str | None = None


class HealthCheck(BaseModel):
    name: str
    status: Status
    detail: str
    hint: str | None = None


class HealthReport(BaseModel):
    checks: list[HealthCheck]

    @property
    def failed(self) -> bool:
        return any(c.status == "fail" for c in self.checks)


class ToolInfo(BaseModel):
    name: str
    command: str
    available: bool
    version: str | None = None
    note: str | None = None


class ContainerInfo(BaseModel):
    id: str
    name: str
    image: str
    state: str
    status: str
    ports: list[str] = Field(default_factory=list)


class DockerStatus(BaseModel):
    cli_installed: bool
    socket_path: str
    reachable: bool
    server_version: str | None = None
    error: str | None = None
    hint: str | None = None
    containers: list[ContainerInfo] = Field(default_factory=list)


class OllamaModel(BaseModel):
    name: str
    size_bytes: int = 0
    modified_at: datetime | None = None
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None


class OllamaStatus(BaseModel):
    endpoint: str
    cli_installed: bool
    reachable: bool
    version: str | None = None
    error: str | None = None
    hint: str | None = None


class UpgradablePackage(BaseModel):
    name: str
    current_version: str | None
    candidate_version: str
    origin: str | None = None
    security: bool = False  # the candidate is published in a -security pocket


class CleanupItem(BaseModel):
    id: str
    description: str
    reclaimable_bytes: int | None
    privileged: bool
    command: list[str] | None = None
    paths: list[str] = Field(default_factory=list)
