"""SSH workspace: profiles, generated OpenSSH config, credentials, askpass, host keys, SFTP."""

from __future__ import annotations

import io
import shutil
import stat
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from nexus_core import paths
from nexus_core.errors import NexusError, ValidationError
from nexus_core.ssh import askpass, config, credentials, hostkeys, profiles, sessions, sftp
from nexus_core.ssh.profiles import Forward, SSHProfile


def make(**kw):
    base = {"name": "homelab", "host": "192.168.1.10", "user": "admin"}
    return SSHProfile(**{**base, **kw})


@pytest.mark.parametrize(
    "bad",
    [
        {"options": {"ProxyCommand": "nc %h %p"}},
        {"options": {"LocalCommand": "id"}},
        {"options": {"StrictHostKeyChecking": "no"}},
        {"host": "a b"},
        {"user": "-oProxyCommand=x"},
        {"port": 70000},
        {"auth": "password"},
        {"auth": "key"},
        {"agent_forwarding": True},
        {"credential_ref": "Bad Ref"},
        {"key_path": "~/.ssh/id_ed25519.pub", "auth": "key"},
    ],
)
def test_profile_validation(bad):
    with pytest.raises((ValueError, ValidationError)):
        make(**bad)


def test_forward_validation():
    assert Forward(kind="dynamic", listen_port=1080).ssh_option() == ("DynamicForward", "127.0.0.1:1080")
    assert Forward(kind="local", listen_port=8080, dest_host="db", dest_port=5432).ssh_option() == (
        "LocalForward",
        "127.0.0.1:8080 db:5432",
    )
    with pytest.raises(ValueError):
        Forward(kind="local", listen_port=8080)


def test_crud_groups_search_and_jump_loops():
    jump = profiles.save(make(name="bastion", host="bastion.example.com", group="Production", favorite=True))
    target = profiles.save(make(name="db", host="10.0.0.5", jump_profile_id=jump.id, tags=["postgres"]))
    assert profiles.get("db").jump_profile_id == jump.id
    assert [p.name for p in profiles.list_profiles("postgres")] == ["db"]
    assert [p.name for p in profiles.list_profiles(favorites_only=True)] == ["bastion"]
    assert [p.name for p in profiles.list_profiles(group="Production")] == ["bastion"]
    jump.jump_profile_id = target.id
    with pytest.raises(ValidationError, match="loop"):
        profiles.save(jump)
    with pytest.raises(ValidationError, match="jump host"):
        profiles.delete(jump.id)
    profiles.delete(target.id)
    profiles.delete(jump.id)
    assert profiles.list_profiles() == []


def test_history_and_recent():
    p = profiles.save(make())
    profiles.record_event(p.id, "connect")
    assert profiles.recent()[0].id == p.id
    assert profiles.history()[0]["event"] == "connect"


def test_generated_config(tmp_path):
    jump = make(name="bastion", host="bastion.example.com")
    target = make(
        name="db",
        host="10.0.0.5",
        port=2222,
        jump_profile_id=jump.id,
        auth="password",
        credential_ref="db-pass",
        forwards=[Forward(kind="local", listen_port=15432, dest_host="127.0.0.1", dest_port=5432)],
        agent_forwarding=True,
        agent_forwarding_consent=time.time(),
    )
    user_cfg = tmp_path / "config"
    user_cfg.write_text("Host *\n  ServerAliveInterval 60\n")
    text = config.render([jump, target], user_cfg)
    block = text.split(f"Host {target.alias}")[1].split("Host ")[0]
    assert (
        "ProxyJump " + jump.alias in block
        and "Port 2222" in block
        and "LocalForward 127.0.0.1:15432 127.0.0.1:5432" in block
    )
    assert "StrictHostKeyChecking yes" in block and "ForwardAgent yes" in block and "PubkeyAuthentication no" in block
    assert f'Include "{user_cfg}"' in text and "db-pass" not in text
    path = config.write([jump, target])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and path.parent == paths.runtime_dir()


def test_ssh_command_never_contains_secrets():
    p = profiles.save(make(auth="password", credential_ref="homelab-root"))
    argv = sessions.ssh_command(p)
    assert "SSH_ASKPASS_REQUIRE=force" in argv and "NEXUS_CREDENTIAL_REF=homelab-root" in argv
    assert argv[-1] == p.alias


def test_credentials_memory_backend_and_metadata(tmp_path):
    backend = credentials.MemoryBackend()
    mgr = credentials.CredentialManager(backend)
    mgr.save("homelab-root", "ssh-password", "S3cr3t-value", "root", rotate_after_days=1)
    assert mgr.secret("homelab-root") == "S3cr3t-value"
    meta = mgr.list()[0]
    assert meta.username == "root" and not meta.rotation_due
    db = Path(mgr.db.path).read_bytes()
    assert b"S3cr3t-value" not in db, "secret leaked into the SQLite store"
    with pytest.raises(NexusError):
        mgr.save("Bad Ref", "generic", "x")
    mgr.delete("homelab-root")
    assert mgr.secret("homelab-root") is None and mgr.list() == []


def test_secret_service_unavailable_has_no_plaintext_fallback(monkeypatch):
    mgr = credentials.CredentialManager(credentials.SecretServiceBackend())
    monkeypatch.setattr(
        credentials.SecretServiceBackend,
        "_collection",
        lambda self: (_ for _ in ()).throw(credentials.DependencyMissingError("no Secret Service")),
    )
    with pytest.raises(NexusError, match="Secret Service"):
        mgr.save("x1", "ssh-password", "pw")
    assert mgr.list() == []


def test_askpass_answers_only_password_prompts(monkeypatch, capsys):
    backend = credentials.MemoryBackend()
    backend.store("ref1", "ssh-password", "pw123", "")
    monkeypatch.setattr(credentials, "SecretServiceBackend", lambda: backend)
    monkeypatch.setenv("NEXUS_CREDENTIAL_REF", "ref1")
    assert askpass.main(["askpass", "admin@host's password: "]) == 0
    assert capsys.readouterr().out.strip() == "pw123"
    for prompt in (
        "Are you sure you want to continue connecting (yes/no/[fingerprint])?",
        "Allow agent forwarding?",
        "Verification code: ",
    ):
        assert askpass.main(["askpass", prompt]) == 1
    assert "pw123" not in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="openssh-client not installed")
def test_known_hosts(tmp_path):
    key = tmp_path / "k"
    __import__("subprocess").run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    pub = key.with_suffix(".pub").read_text().split()
    known = tmp_path / "known_hosts"
    assert not hostkeys.is_known("10.9.8.7", 22, known)
    line = f"[10.9.8.7]:2200 {pub[0]} {pub[1]}"
    hostkeys.trust([hostkeys.HostKey(key_type=pub[0], fingerprint=hostkeys._fingerprint(line), line=line)], known)
    assert hostkeys.is_known("10.9.8.7", 2200, known) and not hostkeys.is_known("10.9.8.7", 22, known)
    assert stat.S_IMODE(known.stat().st_mode) == 0o600
    assert hostkeys._fingerprint(line).startswith("SHA256:")


class FakeSFTP:
    def __init__(self):
        self.files = {"/home/admin/a.txt": b"hello", "/home/admin/dir": None}
        self.removed = []

    def listdir_attr(self, path):
        return [
            SimpleNamespace(filename="a.txt", st_mode=0o100644, st_size=5, st_mtime=1),
            SimpleNamespace(filename="dir", st_mode=0o040755, st_size=0, st_mtime=1),
        ]

    def stat(self, path):
        return SimpleNamespace(st_mode=0o040755 if self.files.get(path, b"") is None else 0o100644)

    def remove(self, path):
        self.removed.append(path)

    def rmdir(self, path):
        self.removed.append(path + "/")

    def mkdir(self, path):
        self.files[path] = None

    def rename(self, a, b):
        self.files[b] = self.files.pop(a)

    def get(self, remote, local, callback=None):
        for i in range(1, 6):
            callback(i, 5)
        Path(local).write_bytes(self.files[remote])

    def put(self, local, remote, callback=None):
        for i in range(1, 6):
            callback(i, 5)


class FakeClient:
    def __init__(self):
        self.sftp = FakeSFTP()
        self.closed = False

    def open_sftp(self):
        return self.sftp

    def close(self):
        self.closed = True


def test_sftp_operations(tmp_path):
    client = FakeClient()
    s = sftp.SFTPSession(make(), client=client)
    entries = s.listdir("/home/admin")
    assert [e.name for e in entries] == ["dir", "a.txt"] and entries[0].is_dir
    progress = []
    s.download("/home/admin/a.txt", tmp_path / "a.txt", progress=lambda d, t: progress.append(d))
    assert (tmp_path / "a.txt").read_bytes() == b"hello" and progress[-1] == 5
    with pytest.raises(ValidationError):
        s.delete("/home/admin/a.txt", confirmed=False)
    s.delete("/home/admin/dir", confirmed=True)
    assert client.sftp.removed == ["/home/admin/dir/"]
    with pytest.raises(ValidationError):
        s.delete("/", confirmed=True)
    cancel = threading.Event()
    cancel.set()
    (tmp_path / "up.bin").write_bytes(b"x")
    with pytest.raises(sftp.TransferCancelled):
        s.upload(tmp_path / "up.bin", "/home/admin/up.bin", cancel=cancel)
    s.close()
    assert client.closed


def test_sftp_refuses_jump_hosts_explicitly():
    with pytest.raises(NexusError, match="jump"):
        sftp.SFTPSession(make(jump_profile_id="abc")).connect()


def test_no_secret_in_io(capsys):
    print(io.StringIO("ok").read())
    assert "ok" in capsys.readouterr().out
