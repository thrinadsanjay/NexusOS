"""Administrative tasks through the user's sudo rights (nexus_core.privilege, nexus-admin).

A fake ``sudo`` reproduces the behaviour of sudo 1.9 / sudo-rs that matters here
(NOPASSWD, password via -S with retries, refusal); the real binaries are exercised in
scripts/validation/sudo-access-container.sh.
"""

from __future__ import annotations

import io
import json
import sys
import textwrap

import pytest
from nexus_core import agent_client, privilege
from nexus_core.errors import NexusError

PASSWORD = "c0rrect-horse"  # test-only value

FAKE_SUDO = textwrap.dedent(
    """\
    #!/bin/bash
    # Started with a minimal environment (like the real one): settings come from files next to it.
    # mode: nopasswd | password | denied; argv (never stdin) is logged to sudo.log
    dir=$(dirname "$0"); mode=$(cat "$dir/mode"); secret=$(cat "$dir/secret"); USER=alice
    echo "$*" >> "$dir/sudo.log"
    if [ "$1" = "-n" ]; then
        shift; [ "$1" = "--" ] && shift
        case "$mode" in
            nopasswd) exec "$@" ;;
            password) echo "sudo: a password is required" >&2; exit 1 ;;
            denied) echo "$USER is not in the sudoers file." >&2; exit 1 ;;
        esac
    fi
    if [ "$1" = "-S" ]; then
        shift 3; [ "$1" = "--" ] && shift
        if [ "$mode" = denied ]; then IFS= read -r pw; echo "$USER is not in the sudoers file." >&2; exit 1; fi
        for try in 1 2 3; do
            IFS= read -r pw || { echo "sudo: no password was provided" >&2; exit 1; }
            if [ "$pw" = "$secret" ]; then exec "$@"; fi
            echo "Sorry, try again." >&2
        done
        echo "sudo: 3 incorrect password attempts" >&2; exit 1
    fi
    exit 2
    """
)

FAKE_HELPER = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, sys
    print(json.dumps({"type": "hello", "uid": 1000}), flush=True)
    req = json.loads(sys.stdin.readline())
    print(json.dumps({"type": "progress", "percent": 50.0}), flush=True)
    if req["op"] == "fail.op":
        print(json.dumps({"type": "error", "code": "failed", "message": "boom"}), flush=True)
    else:
        print(json.dumps({"type": "result", "ok": True, "data": {"op": req["op"], "params": req["params"]}}), flush=True)
    """
)


def _profile(admin="sudo", groups=("users", "sudo")):
    return privilege.AccessProfile(
        user="alice",
        uid=1000,
        groups=list(groups),
        admin=admin,
        reason="test",
        sudo_available=True,
        docker=False,
        journal=False,
        libvirt=False,
    )


@pytest.fixture
def fake_sudo(tmp_path, monkeypatch):
    sudo, helper, log = tmp_path / "sudo", tmp_path / "nexus-admin", tmp_path / "sudo.log"
    sudo.write_text(FAKE_SUDO)
    helper.write_text(FAKE_HELPER.replace("/usr/bin/env python3", sys.executable))
    sudo.chmod(0o755)
    helper.chmod(0o755)
    monkeypatch.setenv("NEXUSOS_SUDO", str(sudo))
    monkeypatch.setenv("NEXUSOS_ADMIN_HELPER", str(helper))
    (tmp_path / "secret").write_text(PASSWORD + "\n")
    monkeypatch.delenv("NEXUSOS_ADMIN_TRANSPORT", raising=False)
    monkeypatch.setattr(privilege, "_profile", None)
    monkeypatch.setattr(privilege, "build_profile", _profile)
    monkeypatch.setattr(privilege, "AUTH_TIMEOUT_S", 10.0)
    asked: list[privilege.AuthRequest] = []

    def use(mode: str, answers: list[str | None] | None = None, profile=None):
        (tmp_path / "mode").write_text(mode + "\n")
        if profile is not None:
            monkeypatch.setattr(privilege, "build_profile", lambda: profile)
        queue = list(answers or [])

        def provider(req: privilege.AuthRequest):
            asked.append(req)
            return queue.pop(0) if queue else None

        privilege.set_password_provider(provider)
        return asked

    yield use, log
    privilege.set_password_provider(None)


def test_passwordless_sudo_runs_without_asking(fake_sudo):
    use, log = fake_sudo
    asked = use("nopasswd")
    events = []
    data = agent_client.call("apt.install", {"packages": ["hello"]}, on_event=events.append, label="Install hello")
    assert data == {"op": "apt.install", "params": {"packages": ["hello"]}}
    assert events and events[0]["type"] == "progress"
    assert asked == []
    assert privilege.access().auth == "not-required"
    assert log.read_text().startswith("-n -- ")


def test_password_sudo_shows_the_password_box_once(fake_sudo):
    use, log = fake_sudo
    asked = use("password", [PASSWORD])
    assert agent_client.call("service.control", {"unit": "nginx.service", "action": "restart"}, label="Restart nginx")
    assert (
        len(asked) == 1 and asked[0].action == "Restart nginx" and asked[0].user == "alice" and asked[0].error is None
    )
    assert privilege.access().auth == "required"
    assert PASSWORD not in log.read_text()  # the password never appears in argv


def test_wrong_password_retries_with_a_message(fake_sudo):
    use, _ = fake_sudo
    asked = use("password", ["nope", PASSWORD])
    assert agent_client.call("system.ntp", {"enabled": True})
    assert [r.attempt for r in asked] == [1, 2]
    assert asked[1].error == "Incorrect password, try again"


def test_three_wrong_passwords_fail(fake_sudo):
    use, _ = fake_sudo
    use("password", ["a", "b", "c"])
    with pytest.raises(privilege.AccessDeniedError, match="Authentication failed"):
        agent_client.call("system.ntp", {"enabled": True})


def test_cancelling_the_password_box(fake_sudo):
    use, _ = fake_sudo
    use("password", [None])
    with pytest.raises(privilege.AuthCancelledError):
        agent_client.call("system.ntp", {"enabled": True})


def test_user_without_sudo_is_denied_without_a_prompt(fake_sudo):
    use, _ = fake_sudo
    asked = use("password", [PASSWORD], profile=_profile(admin="none", groups=("users",)))
    with pytest.raises(privilege.AccessDeniedError, match="Access denied"):
        agent_client.call("apt.install", {"packages": ["hello"]})
    assert asked == []


def test_sudoers_refusal_after_password_is_access_denied(fake_sudo):
    use, _ = fake_sudo
    use("denied", [PASSWORD])
    with pytest.raises(privilege.AccessDeniedError) as exc:
        agent_client.call("apt.install", {"packages": ["hello"]})
    assert "sudoers" in (exc.value.hint or "")


def test_nopasswd_rule_for_a_non_member_is_honoured(fake_sudo):
    use, _ = fake_sudo
    use("nopasswd", profile=_profile(admin="none", groups=("users",)))
    assert agent_client.call("agent.ping")
    assert privilege.access().admin == "sudo"


def test_helper_errors_surface_as_agent_errors(fake_sudo):
    use, _ = fake_sudo
    use("nopasswd")
    with pytest.raises(agent_client.AgentError, match="boom"):
        agent_client.call("fail.op")


def test_missing_helper(fake_sudo, monkeypatch, tmp_path):
    use, _ = fake_sudo
    use("nopasswd")
    monkeypatch.setenv("NEXUSOS_ADMIN_HELPER", str(tmp_path / "absent"))
    assert not agent_client.available()
    with pytest.raises(NexusError, match="not installed"):
        agent_client.call("agent.ping")


def test_profile_classification(monkeypatch):
    monkeypatch.setenv("NEXUSOS_SUDO", "/usr/bin/sudo")
    monkeypatch.setattr(privilege.os, "getuid", lambda: 1000)
    monkeypatch.setattr(
        privilege.pwd, "getpwuid", lambda uid: type("P", (), {"pw_name": "alice", "pw_gecos": "Alice A,,,"})()
    )
    monkeypatch.setattr(privilege, "_group_names", lambda: ["alice", "sudo", "adm"])
    p = privilege.build_profile()
    assert (p.admin, p.journal, p.full_name, p.can_admin) == ("sudo", True, "Alice A", True)
    monkeypatch.setattr(privilege, "_group_names", lambda: ["alice", "docker"])
    p = privilege.build_profile()
    assert p.admin == "none" and not p.can_admin and "sudo group" in p.reason
    monkeypatch.delenv("NEXUSOS_SUDO")
    monkeypatch.setattr(privilege.shutil, "which", lambda _: None)
    assert privilege.build_profile().reason == "sudo is not installed"


# ------------------------------------------------------------------ nexus-admin helper
def _run_admin(monkeypatch, argv, stdin_text, euid=0, sudo_uid="1000"):
    from nexus_agent import admin

    out = io.StringIO()
    monkeypatch.setattr(admin.os, "geteuid", lambda: euid)
    monkeypatch.setenv("SUDO_UID", sudo_uid)
    monkeypatch.setattr(admin.sys, "stdout", out)
    monkeypatch.setattr(admin.sys, "stdin", io.StringIO(stdin_text))
    monkeypatch.setattr(admin.signal, "signal", lambda *a: None)
    code = admin.main(argv)
    return code, [json.loads(line) for line in out.getvalue().splitlines()]


def test_nexus_admin_runs_one_allow_listed_op_and_audits(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUSOS_AGENT_AUDIT", str(tmp_path / "audit.log"))
    code, events = _run_admin(monkeypatch, ["run"], json.dumps({"v": 1, "op": "agent.ping", "params": {}}) + "\n")
    assert code == 0 and events[0]["type"] == "hello" and events[-1]["type"] == "result"
    entry = json.loads((tmp_path / "audit.log").read_text().splitlines()[-1])
    assert entry["via"] == "sudo" and entry["uid"] == 1000 and entry["outcome"] == "ok"


def test_nexus_admin_rejects_unknown_ops_and_bad_params(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUSOS_AGENT_AUDIT", str(tmp_path / "audit.log"))
    _, events = _run_admin(monkeypatch, ["run"], json.dumps({"v": 1, "op": "shell.exec", "params": {}}) + "\n")
    assert events[-1]["code"] == "unknown-op"
    req = {"v": 1, "op": "service.control", "params": {"unit": "sshd-evil.service", "action": "stop"}}
    _, events = _run_admin(monkeypatch, ["run"], json.dumps(req) + "\n")
    assert events[-1]["code"] == "invalid"
    _, events = _run_admin(monkeypatch, ["run"], "not json\n")
    assert events[-1]["code"] == "bad-request"


def test_nexus_admin_refuses_without_root(monkeypatch):
    code, events = _run_admin(monkeypatch, ["run"], "", euid=1000)
    assert code == 77 and events[0]["code"] == "unauthorized"
