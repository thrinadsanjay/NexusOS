"""Docker Engine client, Compose wrapper and the Nexus application platform."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import httpx
import pytest
import yaml
from nexus_core import compose, runner
from nexus_core import docker as engine
from nexus_core.apps import lifecycle, registry
from nexus_core.errors import DependencyMissingError, NexusError, ValidationError

CONTAINERS = [
    {
        "Id": "abcdef1234567890",
        "Names": ["/web"],
        "Image": "nginx",
        "State": "running",
        "Status": "Up",
        "Ports": [{"IP": "127.0.0.1", "PrivatePort": 80, "PublicPort": 8080, "Type": "tcp"}],
        "Labels": {
            "com.docker.compose.project": "shop",
            "com.docker.compose.service": "web",
            "com.docker.compose.project.config_files": "/srv/shop/compose.yaml",
        },
    }
]


def docker_transport(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        p = request.url.path.replace("/v1.43", "")
        if p == "/containers/json":
            return httpx.Response(200, json=CONTAINERS)
        if p.endswith("/json") and p.startswith("/containers/"):
            return httpx.Response(200, json={"Config": {"Env": ["DB_PASSWORD=secret", "PATH=/bin"]}, "Name": "/web"})
        if p.endswith("/logs"):
            frame = b"\x01\x00\x00\x00\x00\x00\x00\x0ctoken=abc12\n"
            return httpx.Response(200, content=frame)
        if p.endswith("/stats"):
            return httpx.Response(
                200,
                json={
                    "cpu_stats": {"cpu_usage": {"total_usage": 200}, "system_cpu_usage": 1000, "online_cpus": 2},
                    "precpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 500},
                    "memory_stats": {"usage": 1000, "limit": 4000, "stats": {"inactive_file": 200}},
                },
            )
        if p == "/images/create":
            return httpx.Response(200, content=b'{"status":"Pulling"}\n{"status":"Done"}\n')
        if request.method == "POST" and p.startswith("/containers/") and p.endswith("/start"):
            return httpx.Response(204)
        if p == "/containers/missing/stop":
            return httpx.Response(404, json={"message": "No such container: missing"})
        return httpx.Response(200, json={})

    return httpx.MockTransport(handler)


def test_docker_client_operations():
    calls = []
    with engine.DockerClient(transport=docker_transport(calls)) as c:
        assert c.containers()[0].ports == ["127.0.0.1:8080->80/tcp"]
        c.container_action("web", "start")
        inspected = c.inspect_container("web")
        assert "secret" not in json.dumps(inspected)
        assert "abc12" not in c.logs("web")
        stats = c.stats("web")
        assert stats["cpu_percent"] == 40.0 and stats["memory_bytes"] == 800
        assert [e["status"] for e in c.pull("nginx:1.27")] == ["Pulling", "Done"]
        assert c.compose_projects()[0]["name"] == "shop"
        with pytest.raises(NexusError, match="No such container"):
            c.container_action("missing", "stop")
        with pytest.raises(NexusError):
            c.container_action("web", "exec")
        with pytest.raises(ValidationError):
            c.container_action("../../etc", "start")


def test_docker_missing_socket(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCKER_HOST", f"unix://{tmp_path}/nope.sock")
    with pytest.raises(DependencyMissingError):
        engine.DockerClient()


def test_docker_permission_denied(monkeypatch, tmp_path):
    import socket

    sock_path = tmp_path / "d.sock"
    s = socket.socket(socket.AF_UNIX)
    s.bind(str(sock_path))
    monkeypatch.setenv("DOCKER_HOST", f"unix://{sock_path}")
    monkeypatch.setattr(os, "access", lambda *a, **k: False)
    with pytest.raises(NexusError, match="permission denied"):
        engine.DockerClient()
    s.close()


def test_compose_argv_and_env_file(tmp_path, monkeypatch):
    f = tmp_path / "compose.yaml"
    f.write_text("services: {}\n")
    seen = []
    monkeypatch.setattr(compose, "require_compose", lambda: None)
    monkeypatch.setattr(
        runner,
        "run",
        lambda argv, timeout=0, env=None: seen.append(argv) or runner.CommandResult(tuple(argv), 0, "", ""),
    )
    compose.run_action("shop", [f], "up")
    assert seen[0][:4] == ["docker", "compose", "-p", "shop"] and seen[0][-3:] == ["up", "-d", "--remove-orphans"]
    for bad in ("Shop", "a b", "../x"):
        with pytest.raises(ValidationError):
            compose.run_action(bad, [f], "up")
    with pytest.raises(ValidationError):
        compose.run_action("shop", [f], "exec")
    env = tmp_path / ".env"
    compose.write_env_file(env, {"DB_PASSWORD": "x"})
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    with pytest.raises(ValidationError):
        compose.write_env_file(env, {"BAD": "x\nINJECT=1"})


def test_repository_registry_is_valid():
    apps = registry.load_registry()
    assert set(apps) == {"private-cloud", "nexusops", "cloud-desktop", "open-webui", "ansible-ui"}
    assert apps["ansible-ui"].status == "unavailable" and not apps["ansible-ui"].installable
    for app in apps.values():
        for port in app.ports:
            assert port.bind == "127.0.0.1"
        if app.deployment and app.deployment.source_repo:
            assert len(app.deployment.source_ref) == 40


def test_nexusops_override_removes_docker_socket(repo_root):
    override = (repo_root / "applications/nexusops/compose.nexusos.yaml").read_text()
    assert "docker.sock" not in override.replace("Removes the Docker socket mount", "")
    assert "!override" in override


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["ports"].append({"name": "x", "host_port": 1, "bind": "0.0.0.0"}),
        lambda d: d["deployment"].update(source_ref="main"),
        lambda d: d.update(status="planned", status_reason=""),
        lambda d: d.update(health={"url": "http://10.0.0.1:80/"}),
    ],
)
def test_registry_schema_rejections(repo_root, mutation):
    data = yaml.safe_load((repo_root / "applications/registry/private-cloud.yaml").read_text())
    mutation(data)
    with pytest.raises(ValueError):
        registry.AppDefinition(**data)


@pytest.fixture
def mini_registry(tmp_path):
    root = tmp_path / "apps"
    (root / "registry").mkdir(parents=True)
    (root / "hello").mkdir()
    (root / "hello" / "compose.yaml").write_text(
        "services:\n  web:\n    image: nginx:1.27\n    ports: ['127.0.0.1:18080:80']\n"
    )
    (root / "registry" / "hello.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "hello",
                "name": "Hello",
                "version": "1.0",
                "summary": "test",
                "status": "available",
                "deployment": {"project": "nexus-hello", "files": ["compose.yaml"], "backup_volumes": []},
                "config": [
                    {"key": "SECRET_KEY", "secret": True, "generate": "token"},
                    {"key": "MODE", "default": "prod"},
                ],
                "ports": [{"name": "web", "host_port": 18080}],
                "health": {"url": "http://127.0.0.1:18080/"},
                "gateway": {"suggested_hostname": "hello.nexus.lan", "backend_port": 18080},
            }
        )
    )
    return root


def test_build_env_generates_and_keeps_secrets(mini_registry):
    app = registry.get("hello", mini_registry)
    env = lifecycle.build_env(app)
    assert len(env["SECRET_KEY"]) > 30 and env["MODE"] == "prod"
    assert lifecycle.build_env(app, existing=env)["SECRET_KEY"] == env["SECRET_KEY"]
    with pytest.raises(ValidationError):
        lifecycle.build_env(app, {"UNKNOWN": "1"})


def test_lifecycle_with_fake_compose(mini_registry, monkeypatch):
    actions = []
    monkeypatch.setattr(lifecycle, "check_dependencies", lambda app: [])
    monkeypatch.setattr(compose, "validate", lambda *a, **k: (True, ""))
    monkeypatch.setattr(
        compose, "run_action", lambda project, files, action, env=None, timeout=0: actions.append(action)
    )
    monkeypatch.setattr(compose, "ps", lambda *a, **k: [{"Service": "web", "State": "running", "Health": ""}])
    monkeypatch.setattr(lifecycle, "health", lambda app, transport=None: "healthy")
    state = lifecycle.install("hello", root=mini_registry)
    assert state.installed and state.status == "running" and state.urls == ["http://127.0.0.1:18080"]
    env_file = lifecycle.app_dir("hello") / ".env"
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    first_secret = env_file.read_text()
    lifecycle.action("hello", "restart", root=mini_registry)
    lifecycle.update("hello", root=mini_registry)
    assert env_file.read_text() == first_secret, "update must keep generated secrets"
    lifecycle.uninstall("hello", root=mini_registry)
    assert actions == ["up", "restart", "pull", "up", "down"]
    assert "hello" not in lifecycle.installed_ids()
    route = lifecycle.suggested_route(registry.get("hello", mini_registry))
    assert route["approved"] is False and route["access"] == "lan" and route["backend_host"] == "127.0.0.1"


def test_install_blocked_by_dependencies(mini_registry, monkeypatch):
    monkeypatch.setattr(runner, "which", lambda p: None)
    with pytest.raises(DependencyMissingError) as exc:
        lifecycle.install("hello", root=mini_registry)
    assert "Docker Engine is not installed" in exc.value.hint
    with pytest.raises(NexusError, match="not installed"):
        lifecycle.action("hello", "start", root=mini_registry)


def test_unavailable_app_cannot_install(monkeypatch):
    with pytest.raises(DependencyMissingError) as exc:
        lifecycle.install("ansible-ui")
    assert "unavailable" in exc.value.hint


def test_health_check():
    app = registry.get("open-webui")
    ok = httpx.MockTransport(lambda r: httpx.Response(200))
    bad = httpx.MockTransport(lambda r: httpx.Response(503))
    assert lifecycle.health(app, ok) == "healthy" and lifecycle.health(app, bad) == "unhealthy (503)"


def test_backup_archive_is_private(mini_registry, monkeypatch, tmp_path):
    monkeypatch.setattr(lifecycle, "check_dependencies", lambda app: [])
    monkeypatch.setattr(compose, "validate", lambda *a, **k: (True, ""))
    monkeypatch.setattr(compose, "run_action", lambda *a, **k: None)
    lifecycle.install("hello", root=mini_registry)
    archive = lifecycle.backup("hello", tmp_path / "backups", root=mini_registry)
    assert archive.exists() and stat.S_IMODE(archive.stat().st_mode) == 0o600
    with pytest.raises(ValidationError):
        lifecycle.restore("hello", archive, confirmed=False, root=mini_registry)
    assert Path(archive).name.startswith("hello-")
