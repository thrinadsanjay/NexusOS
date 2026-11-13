"""Management agent: protocol, authorization, validation, apt progress/cancel, audit, idle exit."""

from __future__ import annotations

import json
import os
import socket
import stat
import threading
import time
from pathlib import Path

import pytest
from nexus_agent import ops, server
from nexus_agent.auth import Peer
from nexus_core import agent_client


class DenyAll:
    def authorize(self, peer: Peer, action_id: str):
        return False, "denied by test"


class AllowAll:
    def __init__(self):
        self.seen = []

    def authorize(self, peer: Peer, action_id: str):
        self.seen.append(action_id)
        return True, "test"


@pytest.fixture
def agent(tmp_path):
    def start(authorizer=None, idle=0.0):
        path = tmp_path / "agent.sock"
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(path))
        sock.listen(8)
        a = server.Agent(sock, idle, authorizer or AllowAll())
        t = threading.Thread(target=a.serve, daemon=True)
        t.start()
        return a, path, t

    return start


def test_ping_and_unknown_op(agent):
    _, path, _ = agent()
    assert agent_client.call("agent.ping", socket_path=path)["version"] == "0.2.0"
    with pytest.raises(agent_client.AgentError) as exc:
        agent_client.call("shell.exec", {"cmd": "id"}, socket_path=path)
    assert exc.value.code == "unknown-op"


def test_invalid_parameters(agent):
    _, path, _ = agent()
    for params in ({"packages": ["-oFoo=1"]}, {"packages": ["hello"], "extra": True}, {"packages": "hello"}):
        with pytest.raises(agent_client.AgentError) as exc:
            agent_client.call("apt.install", params, socket_path=path)
        assert exc.value.code == "invalid"


def test_unauthorized(agent, tmp_path):
    _, path, _ = agent(DenyAll())
    with pytest.raises(agent_client.AgentError) as exc:
        agent_client.call("gateway.apply", socket_path=path)
    assert exc.value.code == "unauthorized"
    audit = (tmp_path / "audit.log").read_text()
    assert '"outcome": "denied"' in audit and '"op": "gateway.apply"' in audit


def test_every_mutating_operation_requires_polkit():
    for name, operation in ops.REGISTRY.items():
        if name != "agent.ping":
            assert operation.action and operation.action.startswith("org.nexusos.agent."), name


def test_polkit_policy_declares_every_action(repo_root):
    policy = (repo_root / "command-center/privileged-agent/polkit/org.nexusos.agent.policy").read_text()
    for operation in ops.REGISTRY.values():
        if operation.action:
            assert f'id="{operation.action}"' in policy


def test_malformed_and_oversized_requests(agent):
    _, path, _ = agent()
    for payload in (b"not json\n", b'{"v": 2, "op": "agent.ping"}\n', b"x" * (server.MAX_REQUEST + 10) + b"\n"):
        s = socket.socket(socket.AF_UNIX)
        s.connect(str(path))
        s.sendall(payload)
        reply = json.loads(s.makefile().readline())
        s.close()
        assert reply["type"] == "error" and reply["code"] == "bad-request"


def test_client_reports_missing_agent(tmp_path):
    with pytest.raises(agent_client.AgentUnavailableError):
        agent_client.call("agent.ping", socket_path=tmp_path / "missing.sock")


def test_idle_exit(agent):
    _, _, thread = agent(idle=0.5)
    thread.join(timeout=5)
    assert not thread.is_alive()


FAKE_APT = """#!/usr/bin/env python3
import os, sys, time
fd = int([a for a in sys.argv if a.startswith("APT::Status-Fd=")][0].split("=")[1])
out = os.fdopen(fd, "w")
mode = os.environ.get("FAKE_MODE", "ok")
print("Reading package lists...", flush=True)
for i in range(3):
    out.write(f"dlstatus:{i}:{i * 30}:Retrieving file {i}\\n"); out.flush(); time.sleep(0.2 if mode == "slow" else 0)
if mode == "fail":
    print("E: Sub-process /usr/bin/dpkg returned an error code (1)", flush=True); sys.exit(100)
out.write("pmstatus:hello:50:Installing hello\\n"); out.flush()
print("password=hunter2", flush=True)
sys.exit(0)
"""


def _fake_apt(tmp_path, monkeypatch, mode="ok"):
    script = tmp_path / "apt-get"
    script.write_text(FAKE_APT)
    script.chmod(0o755)
    monkeypatch.setitem(ops.APT_ENV, "FAKE_MODE", mode)
    return str(script)


def test_run_apt_progress_and_redaction(tmp_path, monkeypatch):
    apt = _fake_apt(tmp_path, monkeypatch)
    events = []
    ctx = ops.Context(emit=events.append, cancelled=threading.Event(), uid=0)
    result = ops.run_apt([apt, "-y", "install", "--", "hello"], ctx)
    assert result["ok"]
    phases = [e["phase"] for e in events if e["type"] == "progress"]
    assert phases[:3] == ["download"] * 3 and phases[-1] == "install"
    logs = "\n".join(e["line"] for e in events if e["type"] == "log")
    assert "hunter2" not in logs


def test_run_apt_failure_reports_error(tmp_path, monkeypatch):
    apt = _fake_apt(tmp_path, monkeypatch, "fail")
    ctx = ops.Context(emit=lambda e: None, cancelled=threading.Event(), uid=0)
    with pytest.raises(ops.NexusError, match="status 100"):
        ops.run_apt([apt, "install", "--", "x"], ctx)


def test_run_apt_cancel_during_download(tmp_path, monkeypatch):
    apt = _fake_apt(tmp_path, monkeypatch, "slow")
    cancel = threading.Event()
    events = []

    def emit(e):
        events.append(e)
        if e.get("type") == "progress":
            cancel.set()

    result = ops.run_apt([apt, "install", "--", "x"], ops.Context(emit=emit, cancelled=cancel, uid=0))
    assert result.get("cancelled") is True
    assert not any(e.get("phase") == "install" for e in events if e["type"] == "progress")


def test_apt_operation_refuses_when_busy(monkeypatch):
    assert ops._apt_lock.acquire(blocking=False)
    try:
        with pytest.raises(ops.AgentBusyError):
            ops._apt_operation(
                "install", ops.AptParams(packages=["hello"]), ops.Context(lambda e: None, threading.Event(), 0)
            )
    finally:
        ops._apt_lock.release()


def test_repo_ops_only_touch_nexusos_files(tmp_path, monkeypatch):
    monkeypatch.setattr(ops.packages, "SOURCES_DIR", tmp_path)
    (tmp_path / "ubuntu.sources").write_text("keep")
    ctx = ops.Context(lambda e: None, threading.Event(), 0)
    with pytest.raises(ops.ValidationError):
        ops._repo_remove(ops.RepoRemove(name="ubuntu"), ctx)
    assert (tmp_path / "ubuntu.sources").exists()


def test_cert_import_requires_files_readable_by_caller(tmp_path):
    cert = tmp_path / "c.pem"
    cert.write_text("x")
    cert.chmod(0o600)
    os.chown(cert, 0, 0) if os.getuid() == 0 else None
    with pytest.raises(ops.ValidationError):
        ops._cert_import(
            ops.CertImport(name="x", cert_file=str(cert), key_file=str(cert)),
            ops.Context(lambda e: None, threading.Event(), uid=4242),
        )


def test_systemd_units(repo_root):
    sock = (repo_root / "command-center/privileged-agent/systemd/nexusos-agent.socket").read_text()
    svc = (repo_root / "command-center/privileged-agent/systemd/nexusos-agent.service").read_text()
    assert "SocketMode=0660" in sock and "SocketGroup=sudo" in sock
    assert "--idle-timeout" in svc and "Restart=no" in svc and "[Install]" not in svc


def test_dev_socket_permissions(tmp_path):
    path = tmp_path / "dev.sock"
    t = threading.Thread(target=server.main, args=(["--socket", str(path), "--idle-timeout", "0.5"],), daemon=True)
    t.start()
    for _ in range(50):
        if path.exists():
            break
        time.sleep(0.05)
    assert stat.S_IMODE(path.stat().st_mode) == 0o660
    t.join(timeout=5)
    assert not Path(path).exists()
