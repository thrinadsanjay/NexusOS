"""Shared test helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SOURCES = (
    REPO_ROOT / "command-center" / "backend",
    REPO_ROOT / "command-center" / "privileged-agent",
    REPO_ROOT / "command-center" / "frontend",
    REPO_ROOT / "packages" / "nexus-cli",
)
for _src in PYTHON_SOURCES:
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))


def load_script(relative: str) -> ModuleType:
    """Import a repository script (e.g. scripts/validation/x.py) as a module."""
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT
