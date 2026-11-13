"""Input validation, SSRF prevention, secret redaction and the local store."""

from __future__ import annotations

import os
import stat

import pytest
from nexus_core import activity, notifications, validation
from nexus_core.errors import ValidationError
from nexus_core.redact import REDACTED, redact, redact_text
from nexus_core.store import Store


@pytest.mark.parametrize("name", ["nginx", "python3-yaml", "g++", "libc6:amd64", "linux-image-6.20.0-10-generic"])
def test_valid_package_names(name):
    assert validation.package_name(name) == name


@pytest.mark.parametrize("name", ["-o", "--allow-remove-essential", "Nginx", "a b", "x;rm -rf /", "", "a", "$(id)"])
def test_package_name_injection_rejected(name):
    with pytest.raises(ValidationError):
        validation.package_name(name)


@pytest.mark.parametrize("host", ["cloud.nexus.lan", "a-b.example.com", "localhost"])
def test_hostnames(host):
    assert validation.hostname(host) == host


@pytest.mark.parametrize(
    "host", ["-bad.lan", "a..b", "a.lan; include /etc/shadow", "x" * 70 + ".lan", "white space.lan", ""]
)
def test_bad_hostnames(host):
    with pytest.raises(ValidationError):
        validation.hostname(host)


@pytest.mark.parametrize("port", [0, 65536, "x", -1])
def test_bad_ports(port):
    with pytest.raises(ValidationError):
        validation.port(port)


@pytest.mark.parametrize("dest", ["169.254.169.254", "0.0.0.0", "224.0.0.1", "fe80::1", "100.100.100.200"])
def test_ssrf_forbidden_backends(dest):
    with pytest.raises(ValidationError):
        validation.backend_destination(dest, allow_public=True)


def test_public_backend_requires_opt_in():
    with pytest.raises(ValidationError):
        validation.backend_destination("8.8.8.8")
    assert validation.backend_destination("8.8.8.8", allow_public=True) == ["8.8.8.8"]


@pytest.mark.parametrize("dest", ["127.0.0.1", "10.1.2.3", "192.168.1.5", "172.20.0.2", "::1", "fd00::5"])
def test_private_backends_allowed(dest):
    assert validation.backend_destination(dest)


def test_path_within(tmp_path):
    (tmp_path / "a").mkdir()
    assert validation.path_within(tmp_path / "a", tmp_path)
    with pytest.raises(ValidationError):
        validation.path_within(tmp_path / ".." / "etc", tmp_path)
    (tmp_path / "link").symlink_to("/etc")
    with pytest.raises(ValidationError):
        validation.path_within(tmp_path / "link" / "passwd", tmp_path)


def test_unit_and_name_validation():
    assert validation.unit_name("nginx.service")
    for bad in ("nginx", "../x.service", "a;b.service"):
        with pytest.raises(ValidationError):
            validation.unit_name(bad)
    with pytest.raises(ValidationError):
        validation.single_line("a\nb")


def test_redact_structures():
    data = {
        "Config": {"Env": ["PATH=/bin", "DB_PASSWORD=hunter2", "API_TOKEN=abc"], "Image": "x"},
        "password": "p",
        "nested": [{"secret_key": "s"}],
        "url": "postgres://user:pw@db/x",
    }
    out = redact(data)
    assert out["Config"]["Env"][0] == "PATH=/bin"
    assert out["Config"]["Env"][1] == f"DB_PASSWORD={REDACTED}"
    assert out["password"] == REDACTED and out["nested"][0]["secret_key"] == REDACTED
    assert "pw@" not in out["url"]
    assert "hunter2" not in str(redact(data, redact_all_env=True))
    assert redact(data, redact_all_env=True)["Config"]["Env"][0] == f"PATH={REDACTED}"


def test_redact_text():
    text = (
        "Authorization: Bearer abcdefghijklmnop\npassword=hunter2 token: xyz\n"
        "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n-----END OPENSSH PRIVATE KEY-----\nhttps://u:p@h/"
    )
    out = redact_text(text)
    for secret in ("abcdefghijklmnop", "hunter2", "xyz", "AAAA", "u:p@"):
        assert secret not in out


def test_store_is_private_and_bounded(tmp_path, monkeypatch):
    s = Store(tmp_path / "db.sqlite")
    assert stat.S_IMODE(os.stat(tmp_path / "db.sqlite").st_mode) == 0o600
    s.set_setting("k", {"a": 1})
    assert s.get_setting("k") == {"a": 1}
    monkeypatch.setitem(__import__("nexus_core.store", fromlist=["LIMITS"]).LIMITS, "activity", 10)
    for i in range(25):
        activity.record("test", f"t{i}", "ok", store=s)
    rows = activity.recent(100, store=s)
    assert len(rows) == 10 and rows[0].target == "t24"


def test_activity_redacts_details(tmp_path):
    s = Store(tmp_path / "db.sqlite")
    activity.record("x", "y", "failed", "password=topsecret", store=s)
    assert "topsecret" not in activity.recent(store=s)[0].detail


def test_notifications_dedupe_mute_dismiss(tmp_path):
    s = Store(tmp_path / "db.sqlite")
    a = notifications.notify("Disk failing", "sda", category="storage", dedupe_key="smart:sda", store=s)
    b = notifications.notify("Disk failing", "sda again", category="storage", dedupe_key="smart:sda", store=s)
    assert a == b
    items = notifications.list_notifications(store=s)
    assert len(items) == 1 and items[0].count == 2
    notifications.set_preference("ai", False, store=s)
    assert notifications.notify("model", category="ai", store=s) is None
    notifications.dismiss(a, store=s)
    assert notifications.unread_count(store=s) == 0
    with pytest.raises(ValueError):
        notifications.notify("x", category="nonsense", store=s)
