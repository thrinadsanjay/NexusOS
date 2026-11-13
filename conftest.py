"""Repository-wide pytest configuration: import paths and per-test state isolation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent
for _src in (
    "command-center/backend",
    "command-center/privileged-agent",
    "command-center/frontend",
    "packages/nexus-cli",
):
    if str(REPO_ROOT / _src) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / _src))


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Every test gets private NexusOS state dirs; nothing touches the real home or /etc."""
    from nexus_core import store

    monkeypatch.setenv("NEXUSOS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NEXUSOS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("NEXUSOS_SYSTEM_CONFIG_DIR", str(tmp_path / "etc-nexusos"))
    monkeypatch.setenv("NEXUSOS_AGENT_SOCKET", str(tmp_path / "agent.sock"))
    monkeypatch.setenv("NEXUSOS_AGENT_AUDIT", str(tmp_path / "audit.log"))
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setattr(store, "_default", None)
    yield
    if store._default is not None:
        store._default.close()
        store._default = None
