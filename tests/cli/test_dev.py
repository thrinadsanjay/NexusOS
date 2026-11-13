"""``nexus dev``: template listing, FastAPI generation and React scaffolding."""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys

import pytest

from nexus_cli.services import scaffold

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None and importlib.util.find_spec("httpx") is not None


def test_dev_list(cli):
    result = cli("dev", "list", "--json")
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert {t["name"] for t in data["templates"]} == {"fastapi", "react"}
    assert any(t["command"] == "python3" for t in data["toolchains"])


def test_dev_list_without_toolchains(cli, no_programs):
    result = cli("dev", "list")
    assert result.exit_code == 0
    assert "not installed" in result.output


def test_create_fastapi_project(cli, tmp_path):
    result = cli("dev", "create", "fastapi", "demo-api", "--path", str(tmp_path))
    assert result.exit_code == 0, result.output
    project = tmp_path / "demo-api"
    expected = [
        "app/__init__.py",
        "app/main.py",
        "tests/test_main.py",
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
        "README.md",
        ".gitignore",
    ]
    for rel in expected:
        assert (project / rel).is_file(), rel
    for py in project.rglob("*.py"):
        ast.parse(py.read_text())
    assert 'name = "demo-api"' in (project / "pyproject.toml").read_text()
    assert "${" not in (project / "README.md").read_text()


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi/httpx not installed in the test environment")
def test_generated_fastapi_project_passes_its_tests(tmp_path):
    scaffold.create_fastapi_project("svc", tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=tmp_path / "svc",
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "2 passed" in proc.stdout


@pytest.mark.parametrize("name", ["Bad", "1abc", "has space", "../escape", "a" * 64, ""])
def test_invalid_project_names_rejected(cli, tmp_path, name):
    result = cli("dev", "create", "fastapi", name, "--path", str(tmp_path))
    assert result.exit_code == 2
    assert not any(tmp_path.iterdir())


def test_existing_non_empty_directory_rejected(cli, tmp_path):
    (tmp_path / "taken").mkdir()
    (tmp_path / "taken" / "file").write_text("keep me")
    result = cli("dev", "create", "fastapi", "taken", "--path", str(tmp_path))
    assert result.exit_code == 2
    assert (tmp_path / "taken" / "file").read_text() == "keep me"


def test_react_dry_run_shows_documented_command(cli, tmp_path):
    result = cli("dev", "create", "react", "web-ui", "--path", str(tmp_path), "--dry-run")
    assert result.exit_code == 0
    assert "npm create vite@latest web-ui -- --template react-ts" in " ".join(result.output.split())
    assert not (tmp_path / "web-ui").exists()


def test_react_without_node_reports_missing_dependency(cli, tmp_path, no_programs):
    result = cli("dev", "create", "react", "web-ui", "--path", str(tmp_path), "--yes")
    assert result.exit_code == 3
    assert "not found" in result.output


def test_react_old_node_rejected(monkeypatch):
    from nexus_cli.core import runner

    monkeypatch.setattr(runner, "which", lambda p: f"/usr/bin/{p}")
    monkeypatch.setattr(runner, "run", lambda *a, **k: runner.CommandResult(("node",), 0, "v16.20.0\n", ""))
    with pytest.raises(scaffold.DependencyMissingError):
        scaffold.check_node()
