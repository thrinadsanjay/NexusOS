"""Installation profiles (manifests/profiles.yaml). Nothing optional is installed automatically."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from nexus_core import paths
from nexus_core.errors import NexusError


class Profile(BaseModel):
    id: str
    name: str
    description: str
    default: bool = False
    manifests: list[str] = Field(default_factory=list)
    packages: list[str] = Field(default_factory=list)
    nexusos_packages: list[str] = Field(default_factory=list)
    applications: list[str] = Field(default_factory=list)
    optional_applications: list[str] = Field(default_factory=list)
    external: list[str] = Field(default_factory=list)


def manifests_dir() -> Path:
    override = os.environ.get("NEXUSOS_MANIFESTS")
    if override:
        return Path(override)
    installed = paths.share_dir() / "manifests"
    return installed if installed.exists() else Path(__file__).resolve().parents[3] / "manifests"


def load() -> list[Profile]:
    data = yaml.safe_load((manifests_dir() / "profiles.yaml").read_text())
    return [Profile(**p) for p in data["profiles"]]


def get(profile_id: str) -> Profile:
    for p in load():
        if p.id == profile_id:
            return p
    raise NexusError(f"unknown profile {profile_id!r}")


def packages_for(profile: Profile) -> list[str]:
    names: list[str] = list(profile.packages) + list(profile.nexusos_packages)
    for manifest in profile.manifests:
        data = yaml.safe_load((manifests_dir() / f"{manifest}.yaml").read_text())
        groups = data.get("packages") or {}
        for group in ("mandatory", "recommended", "optional"):
            names += groups.get(group) or []
    return sorted(set(names))
