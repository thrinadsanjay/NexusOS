"""Version, help, logging and process-runner behaviour."""

from __future__ import annotations

import json

from nexus_cli import __version__
from nexus_cli.core import runner
from nexus_cli.services.release import parse_key_value_file, read_os_release


def test_version_text(cli):
    result = cli("version")
    assert result.exit_code == 0
    assert f"nexus {__version__}" in result.output
    assert "NexusOS CLI" in result.output


def test_version_json(cli):
    result = cli("version", "--json")
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["cli_version"] == __version__ == "0.1.0"
    assert "python_version" in data


def test_root_help_lists_all_groups(cli):
    result = cli("--help")
    assert result.exit_code == 0
    for group in ("version", "help", "system", "dev", "cloud", "infra", "ai"):
        assert group in result.output


def test_help_command(cli):
    result = cli("help")
    assert result.exit_code == 0
    assert "system" in result.output and "infra" in result.output


def test_help_for_group(cli):
    result = cli("help", "system")
    assert result.exit_code == 0
    for command in ("info", "health", "update", "cleanup"):
        assert command in result.output


def test_help_unknown_group(cli):
    result = cli("help", "does-not-exist")
    assert result.exit_code == 2


def test_no_args_shows_help(cli):
    result = cli()
    assert "Usage" in result.output


def test_verbose_and_log_file(cli, tmp_path):
    log_file = tmp_path / "logs" / "nexus.log"
    result = cli("--verbose", "--log-file", str(log_file), "version")
    assert result.exit_code == 0
    assert log_file.exists()


def test_runner_missing_program():
    result = runner.run(["definitely-not-a-real-program-xyz"])
    assert not result.found
    assert not result.ok
    assert result.returncode == 127


def test_runner_success_and_timeout():
    assert runner.run(["true"]).ok
    slow = runner.run(["sleep", "5"], timeout=0.2)
    assert slow.timed_out and not slow.ok


def test_runner_does_not_forward_secrets(monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "do-not-leak")
    monkeypatch.setenv("GITHUB_TOKEN", "do-not-leak")
    env = runner.safe_env()
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "GITHUB_TOKEN" not in env
    result = runner.run(["env"])
    assert "do-not-leak" not in result.stdout


def test_parse_key_value_file_handles_quotes_and_comments():
    text = '# comment\nNAME="NexusOS"\nID=nexusos\nPRETTY_NAME="NexusOS Engineering Edition 1.0"\nBAD LINE\n'
    data = parse_key_value_file(text)
    assert data == {"NAME": "NexusOS", "ID": "nexusos", "PRETTY_NAME": "NexusOS Engineering Edition 1.0"}


def test_read_os_release_from_repo_file(repo_root):
    rel = read_os_release((repo_root / "configs/os-release/os-release",))
    assert rel.is_nexusos
    assert rel.pretty_name == "NexusOS Engineering Edition 1.0"
    assert rel.codename == "resolute"


def test_read_os_release_missing(tmp_path):
    rel = read_os_release((tmp_path / "missing",))
    assert rel.id == "linux" and not rel.is_nexusos
