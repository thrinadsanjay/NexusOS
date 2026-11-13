"""Filesystem locations used by NexusOS management components.

User-level state follows the XDG Base Directory specification. System-level
configuration lives under /etc/nexusos and is written only by the privileged agent.
All locations can be redirected with environment variables for tests and VMs.
"""

from __future__ import annotations

import os
from pathlib import Path


def _xdg(var: str, default: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value and os.path.isabs(value) else Path.home() / default


def data_dir() -> Path:
    """Per-user data (SQLite metadata store, app deployments). Created with mode 0700."""
    path = Path(os.environ.get("NEXUSOS_DATA_DIR") or _xdg("XDG_DATA_HOME", ".local/share") / "nexusos")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    path = Path(os.environ.get("NEXUSOS_CONFIG_DIR") or _xdg("XDG_CONFIG_HOME", ".config") / "nexusos")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/nexusos-{os.getuid()}"  # noqa: S108 - per-uid fallback
    path = Path(base) / "nexusos"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def system_config_dir() -> Path:
    """/etc/nexusos (overridable for tests)."""
    return Path(os.environ.get("NEXUSOS_SYSTEM_CONFIG_DIR", "/etc/nexusos"))


def gateway_dir() -> Path:
    return system_config_dir() / "gateway"


def agent_socket() -> Path:
    return Path(os.environ.get("NEXUSOS_AGENT_SOCKET", "/run/nexusos/agent.sock"))


def share_dir() -> Path:
    """Read-only data shipped by packages (application registry, module manifests)."""
    return Path(os.environ.get("NEXUSOS_SHARE_DIR", "/usr/share/nexusos"))
