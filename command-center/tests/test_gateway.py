"""Gateway: route validation, rendering, activation with nginx -t, rollback, certificates."""

from __future__ import annotations

import shutil
import stat

import httpx
import pytest
import yaml
from nexus_core.errors import ValidationError
from nexus_core.gateway import apply as gw
from nexus_core.gateway import certs, status
from nexus_core.gateway.model import Route, dump_route, find_conflicts, load_routes
from nexus_core.gateway.render import render_route


def route(**kw):
    base = {"id": "app", "hostname": "app.nexus.lan", "backend_port": 8080, "approved": True}
    return Route(**{**base, **kw})


@pytest.mark.parametrize(
    "bad",
    [
        {"hostname": "a.lan;\n include /etc/shadow"},
        {"path_prefix": "/x { return 200; }"},
        {"id": "../etc"},
        {"max_body_size": "1m; evil"},
        {"backend_host": "a b"},
        {"description": "x\nserver { }"},
        {"tls": "letsencrypt", "hostname": "nas.local", "access": "public"},
        {"tls": "imported"},
    ],
)
def test_route_rejects_injection_and_impossible_tls(bad):
    with pytest.raises((ValueError, ValidationError)):
        route(**bad)


def test_render_redirect_tls_websocket_access(tmp_path):
    text = render_route(route(tls="internal-ca", websocket=True, access="lan"), tmp_path, ipv6=True)
    assert "return 301 https://$host$request_uri;" in text
    assert "listen [::]:443 ssl;" in text and "proxy_set_header Upgrade $http_upgrade;" in text
    assert "deny all;" in text and "allow 192.168.0.0/16;" in text
    assert str(tmp_path / "certificates" / "app.nexus.lan" / "privkey.pem") in text
    public = render_route(route(access="public", tls="none"), tmp_path, ipv6=False)
    assert "deny all" not in public and "[::]" not in public


def test_render_letsencrypt_has_acme_location(tmp_path):
    text = render_route(route(tls="letsencrypt", hostname="cloud.example.com", access="public"), tmp_path)
    assert "/.well-known/acme-challenge/" in text and "Strict-Transport-Security" in text


def test_conflicts_and_roundtrip(tmp_path):
    a, b = route(id="a1"), route(id="b1")
    assert find_conflicts([a, b])
    (tmp_path / "a1.yaml").write_text(dump_route(a))
    assert load_routes(tmp_path)[0] == a
    (tmp_path / "zz.yaml").write_text(yaml.safe_dump(route(id="other").model_dump()))
    with pytest.raises(ValidationError):
        load_routes(tmp_path)


def fake_env(tmp_path, test_ok=True, reload_ok=True):
    def cmd(name, ok):
        p = tmp_path / name
        p.write_text(f"#!/bin/sh\necho {name} >> {tmp_path}/calls\n{'exit 0' if ok else 'echo boom >&2; exit 1'}\n")
        p.chmod(0o755)
        return (str(p),)

    return gw.GatewayEnv(
        gateway_dir=tmp_path / "gw", nginx_test=cmd("nginx-test", test_ok), nginx_reload=cmd("nginx-reload", reload_ok)
    )


def write_route(env, r):
    gw.ensure_layout(env)
    (env.routes_dir / f"{r.id}.yaml").write_text(dump_route(r))


def calls(tmp_path):
    p = tmp_path / "calls"
    return p.read_text().split() if p.exists() else []


def test_apply_success_backup_and_state(tmp_path):
    env = fake_env(tmp_path)
    write_route(env, route())
    first = gw.apply(env)
    assert first.ok and first.applied == ["app.conf"]
    assert (env.generated / "app.conf").exists() and (env.gateway_dir / "state.json").exists()
    write_route(env, route(id="two", hostname="two.nexus.lan", backend_port=9000))
    second = gw.apply(env)
    assert second.ok and second.backup and (tmp_path / "gw" / "backups").exists()
    assert calls(tmp_path) == ["nginx-test", "nginx-reload", "nginx-test", "nginx-reload"]
    assert stat.S_IMODE((env.gateway_dir / "backups").stat().st_mode) == 0o700


def test_apply_failed_test_restores_and_never_reloads(tmp_path):
    env = fake_env(tmp_path)
    write_route(env, route())
    assert gw.apply(env).ok
    good = (env.generated / "app.conf").read_text()
    bad_env = fake_env(tmp_path, test_ok=False)
    write_route(bad_env, route(backend_port=9999))
    result = gw.apply(bad_env)
    assert not result.ok and result.rolled_back and "boom" in result.nginx_output
    assert (env.generated / "app.conf").read_text() == good
    assert calls(tmp_path).count("nginx-reload") == 1  # only the first, successful activation


def test_apply_failed_reload_restores_and_reloads_previous(tmp_path):
    env = fake_env(tmp_path)
    write_route(env, route())
    gw.apply(env)
    good = (env.generated / "app.conf").read_text()
    write_route(env, route(backend_port=7000))
    result = gw.apply(fake_env(tmp_path, reload_ok=False))
    assert not result.ok and (env.generated / "app.conf").read_text() == good


def test_apply_refuses_ssrf_and_missing_certs(tmp_path):
    env = fake_env(tmp_path)
    write_route(env, route(backend_host="169.254.169.254"))
    assert "forbidden" in gw.apply(env).message
    shutil.rmtree(env.routes_dir)
    write_route(env, route(tls="internal-ca"))
    assert "certificate files missing" in gw.apply(env).message
    assert calls(tmp_path) == []


def test_pending_routes_are_not_rendered(tmp_path):
    env = fake_env(tmp_path)
    write_route(env, route(approved=False))
    assert gw.apply(env).applied == []


def test_rollback(tmp_path):
    env = fake_env(tmp_path)
    write_route(env, route())
    gw.apply(env)
    write_route(env, route(id="second", hostname="second.nexus.lan"))
    gw.apply(env)
    assert (env.generated / "second.conf").exists()
    result = gw.rollback(env)
    assert result.ok and not (env.generated / "second.conf").exists()


openssl = pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not installed")


@openssl
def test_internal_ca_and_self_signed_certificates(tmp_path):
    gw.ensure_layout(gw.GatewayEnv(gateway_dir=tmp_path))
    certs.issue_internal(tmp_path, "app", ["app.nexus.lan", "*.nexus.lan"])
    certs.issue_self_signed(tmp_path, "test", ["test.nexus.lan"])
    for name in ("app", "test"):
        assert stat.S_IMODE((tmp_path / "certificates" / name / "privkey.pem").stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "ca" / "ca.key").stat().st_mode) == 0o600
    inv = {c.name: c for c in certs.inventory(tmp_path)}
    assert inv["app"].source == "internal-ca" and "app.nexus.lan" in inv["app"].sans and inv["app"].status == "ok"
    assert inv["test"].source == "self-signed" and inv["test"].days_left > 300


@openssl
def test_import_rejects_mismatched_key(tmp_path):
    gw.ensure_layout(gw.GatewayEnv(gateway_dir=tmp_path))
    certs.issue_self_signed(tmp_path, "one", ["one.nexus.lan"])
    certs.issue_self_signed(tmp_path, "two", ["two.nexus.lan"])
    with pytest.raises(ValidationError, match="does not match"):
        certs.import_certificate(
            tmp_path, "mix", tmp_path / "certificates/one/fullchain.pem", tmp_path / "certificates/two/privkey.pem"
        )


def test_letsencrypt_rules(tmp_path):
    for host in ("nas.local", "app.lan", "x.internal", "box.home.arpa", "localhost"):
        with pytest.raises(ValidationError):
            certs.letsencrypt_command(tmp_path, host, "a@b.example")
    cmd = certs.letsencrypt_command(tmp_path, "cloud.example.com", "ops@example.com")
    assert "--webroot" in cmd and str(tmp_path / "acme") in cmd


def test_backend_check_uses_ssrf_guard():
    assert not status.test_backend(route(backend_host="169.254.169.254")).ok
    transport = httpx.MockTransport(lambda req: httpx.Response(204))
    check = status.test_backend(route(), transport=transport)
    assert check.ok and check.status_code == 204
