"""Docker, Ollama and cloud detection, including missing-dependency behaviour."""

from __future__ import annotations

import json

import httpx
import pytest

from nexus_cli.core.errors import ValidationError
from nexus_cli.services import docker, ollama, tools

# ---------------------------------------------------------------- Ollama


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", "http://127.0.0.1:11434"),
        ("0.0.0.0", "http://127.0.0.1:11434"),
        ("127.0.0.1:12345", "http://127.0.0.1:12345"),
        ("https://ollama.lan", "https://ollama.lan:11434"),
        ("http://[::1]:11434", "http://[::1]:11434"),
    ],
)
def test_resolve_endpoint(raw, expected):
    assert ollama.resolve_endpoint(raw) == expected


@pytest.mark.parametrize("raw", ["http://user:pass@host:11434", "ftp://host"])
def test_resolve_endpoint_rejects_unsafe_values(raw):
    with pytest.raises(ValidationError):
        ollama.resolve_endpoint(raw)


def _refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def test_ollama_unavailable_status():
    status = ollama.ollama_status("http://127.0.0.1:11434", transport=httpx.MockTransport(_refuse))
    assert not status.reachable
    assert "not running" in status.error
    assert status.hint


def test_ollama_available_status_and_models():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.12.0"})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "llama3.2:3b",
                            "size": 2019393189,
                            "modified_at": "2026-10-01T10:00:00Z",
                            "details": {"family": "llama", "parameter_size": "3.2B", "quantization_level": "Q4_K_M"},
                        }
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    status = ollama.ollama_status("http://127.0.0.1:11434", transport=transport)
    assert status.reachable and status.version == "0.12.0"
    models = ollama.list_models("http://127.0.0.1:11434", transport=transport)
    assert models[0].name == "llama3.2:3b"
    assert models[0].parameter_size == "3.2B"


def test_cli_ai_status_when_ollama_unavailable(cli, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:9")  # discard port: connection refused
    result = cli("ai", "status")
    assert result.exit_code == 3
    assert "not running" in result.output

    result = cli("ai", "status", "--json")
    assert result.exit_code == 3
    assert json.loads(result.output)["reachable"] is False


def test_cli_ai_models_when_ollama_unavailable(cli, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:9")
    result = cli("ai", "models")
    assert result.exit_code == 3
    assert "not reachable" in result.output


def test_cli_ai_rejects_credentials_in_endpoint(cli, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://admin:secret@127.0.0.1:11434")
    result = cli("ai", "status")
    assert result.exit_code == 2
    assert "secret" not in result.output


# ---------------------------------------------------------------- Docker

CONTAINERS = [
    {
        "Id": "0123456789abcdef",
        "Names": ["/web"],
        "Image": "nginx:1.27",
        "State": "running",
        "Status": "Up 2 hours",
        "Ports": [{"IP": "127.0.0.1", "PrivatePort": 80, "PublicPort": 8080, "Type": "tcp"}],
    },
    {
        "Id": "fedcba987654",
        "Names": ["/job"],
        "Image": "alpine",
        "State": "exited",
        "Status": "Exited (0)",
        "Ports": [],
    },
]


def test_parse_containers():
    parsed = docker.parse_containers(CONTAINERS)
    assert parsed[0].name == "web" and parsed[0].id == "0123456789ab"
    assert parsed[0].ports == ["127.0.0.1:8080->80/tcp"]
    assert parsed[1].state == "exited"


def test_docker_status_via_api():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return httpx.Response(200, json={"Version": "28.2.2"})
        if request.url.path == "/containers/json":
            assert request.url.params["all"] == "true"
            return httpx.Response(200, json=CONTAINERS)
        return httpx.Response(404)

    status = docker.docker_status(transport=httpx.MockTransport(handler))
    assert status.reachable and status.server_version == "28.2.2"
    assert len(status.containers) == 2


def test_docker_missing_socket(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCKER_HOST", f"unix://{tmp_path}/docker.sock")
    status = docker.docker_status()
    assert not status.reachable
    assert "not found" in status.error


def test_docker_tcp_host_not_queried(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://10.0.0.5:2375")
    status = docker.docker_status()
    assert not status.reachable and "non-UNIX" in status.error


def test_cli_infra_containers_without_docker(cli, monkeypatch, tmp_path):
    monkeypatch.setenv("DOCKER_HOST", f"unix://{tmp_path}/missing.sock")
    result = cli("infra", "containers")
    assert result.exit_code == 3
    assert "Docker Engine socket not found" in result.output


def test_cli_infra_status_without_anything(cli, monkeypatch, tmp_path, no_programs):
    monkeypatch.setenv("DOCKER_HOST", f"unix://{tmp_path}/missing.sock")
    result = cli("infra", "status", "--json")
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["docker"]["reachable"] is False
    assert data["podman"]["available"] is False


def test_kvm_status(tmp_path):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("flags\t\t: fpu vme vmx sse\n")
    info = tools.kvm_status(cpuinfo=cpuinfo, dev=tmp_path / "kvm")
    assert not info.available and "missing" in info.note


# ---------------------------------------------------------------- Cloud


def test_cloud_status_without_tools(cli, no_programs):
    result = cli("cloud", "status", "--json")
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert all(not t["available"] for t in data["tools"])
    assert data["kubernetes_context"] is None


def test_cloud_status_never_reads_credentials(cli, monkeypatch, tmp_path):
    aws = tmp_path / ".aws"
    aws.mkdir()
    (aws / "credentials").write_text("[default]\naws_secret_access_key = TOPSECRETVALUE\n")
    (aws / "config").write_text("[default]\nregion = eu-west-1\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    result = cli("cloud", "status", "--json")
    assert result.exit_code == 0
    assert "TOPSECRETVALUE" not in result.output
    assert "eu-west-1" not in result.output


@pytest.mark.parametrize(
    ("text", "version"),
    [("Python 3.14.3", "3.14.3"), ("v22.22.1", "22.22.1"), ("git version 2.51.0", "2.51.0"), ("nothing", None)],
)
def test_extract_version(text, version):
    assert tools.extract_version(text) == version
