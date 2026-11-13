from __future__ import annotations

import pytest
from typer.testing import CliRunner

from nexus_cli.main import app


@pytest.fixture
def cli():
    runner = CliRunner()

    def invoke(*args: str, **kwargs):
        return runner.invoke(app, list(args), **kwargs)

    return invoke


@pytest.fixture
def no_programs(monkeypatch):
    """Simulate a system where no external programs are installed."""
    from nexus_cli.core import runner

    monkeypatch.setattr(runner, "which", lambda program: None)
