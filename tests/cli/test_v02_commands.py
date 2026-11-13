"""CLI v0.2 command groups (packages, ssh, containers, apps, gateway, storage, network, profiles, system)."""

from __future__ import annotations

import json

import pytest
from nexus_core import packages as pk
from nexus_core import runner


def test_new_groups_registered(cli):
    out = cli("--help").output
    for group in ("packages", "ssh", "containers", "apps", "gateway", "storage", "network", "profiles"):
        assert group in out


def test_packages_search_and_plan(cli, monkeypatch):
    monkeypatch.setattr(
        pk, "search", lambda term, limit=30, section=None: [pk.CatalogEntry(name="nginx", summary="web")]
    )
    data = json.loads(cli("packages", "search", "nginx", "--json").output)
    assert data[0]["name"] == "nginx"
    monkeypatch.setattr(
        pk,
        "plan",
        lambda op, names=None: pk.OperationPlan(
            operation=op,
            requested=names or [],
            command=["apt-get", "install", "--", "hello"],
            destructive=False,
            changes=[pk.PlannedChange(action="install", name="hello", new_version="2.10")],
        ),
    )
    result = cli("packages", "install", "hello", "--dry-run")
    assert result.exit_code == 0 and "apt-get install -- hello" in result.output


def test_packages_remove_requires_tty_confirmation(cli, monkeypatch):
    monkeypatch.setattr(
        pk,
        "plan",
        lambda op, names=None: pk.OperationPlan(
            operation=op,
            requested=names,
            command=["apt-get", "remove", "--", "vim"],
            destructive=True,
            changes=[pk.PlannedChange(action="remove", name="vim")],
        ),
    )
    called = []
    monkeypatch.setattr(runner, "run_interactive", lambda *a, **k: called.append(a) or 0)
    result = cli("packages", "remove", "vim")
    assert result.exit_code == 4 and called == []


def test_packages_invalid_name(cli):
    assert cli("packages", "install", "--dry-run", "--", "-oAPT::x=1").exit_code == 2


def test_ssh_add_list_remove_never_prints_secrets(cli):
    result = cli(
        "ssh",
        "add",
        "homelab",
        "admin@192.168.1.10:2222",
        "--group",
        "Homelab",
        "--tag",
        "nas",
        "--forward",
        "L:127.0.0.1:8080:127.0.0.1:80",
    )
    assert result.exit_code == 0, result.output
    data = json.loads(cli("ssh", "list", "--json").output)
    assert data[0]["port"] == 2222 and data[0]["forwards"][0]["kind"] == "local"
    config = cli("ssh", "config").output
    assert "LocalForward 127.0.0.1:8080 127.0.0.1:80" in config
    assert cli("ssh", "add", "bad", "root@x;id").exit_code == 2
    assert cli("ssh", "remove", "homelab").exit_code == 4  # confirmation needs a TTY


def test_ssh_password_profile_requires_credential_ref(cli):
    result = cli("ssh", "add", "pw", "root@10.0.0.2", "--auth", "password")
    assert result.exit_code != 0


def test_containers_without_docker(cli, monkeypatch, tmp_path):
    monkeypatch.setenv("DOCKER_HOST", f"unix://{tmp_path}/none.sock")
    result = cli("containers", "list")
    assert result.exit_code == 3


def test_apps_list_and_status(cli):
    data = json.loads(cli("apps", "list", "--json").output)
    ids = {item["app"]["id"] for item in data}
    assert {"private-cloud", "nexusops", "cloud-desktop", "open-webui", "ansible-ui"} == ids
    status = cli("apps", "status", "ansible-ui")
    assert status.exit_code == 0 and "unavailable" in status.output
    assert cli("apps", "install", "nope", "--yes").exit_code == 1


def test_gateway_commands_without_agent(cli, tmp_path):
    assert json.loads(cli("gateway", "status", "--json").output)["routes_total"] == 0
    assert cli("gateway", "routes", "list").exit_code == 0
    result = cli("gateway", "routes", "add", "app", "app.nexus.lan", "8080")
    assert result.exit_code == 3 and "agent" in result.output
    assert (
        cli("gateway", "routes", "add", "meta", "x.nexus.lan", "80", "--backend-host", "169.254.169.254").exit_code == 2
    )


def test_profiles(cli):
    out = cli("profiles", "list").output
    assert "Base Desktop" in out and "Local AI" in out
    show = cli("profiles", "show", "private-cloud-host").output
    assert "nexusos-gateway" in show and "private-cloud" in show


def test_storage_usage_runs(cli):
    result = cli("storage", "usage", "--json")
    assert result.exit_code == 0
    assert any(u["mount"] == "/" for u in json.loads(result.output))


def test_network_without_networkmanager(cli, monkeypatch):
    monkeypatch.setattr(runner, "which", lambda p: None)
    assert cli("network", "status").exit_code == 3


def test_system_settings_rejects_bad_values(cli):
    assert cli("system", "settings", "hostname", "bad host").exit_code == 2
    assert cli("system", "services", "start", "evil.service").exit_code == 2


@pytest.mark.parametrize("args", [("ai", "pull", "bad model;x"), ("ai", "rm", "x y")])
def test_ai_rejects_bad_model_names(cli, args, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:9")
    assert cli(*args).exit_code in (2, 4)
