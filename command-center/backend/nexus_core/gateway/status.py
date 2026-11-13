"""Unprivileged gateway status: NGINX service, routes, certificates, backend checks."""

from __future__ import annotations

import time
from pathlib import Path

import httpx
from pydantic import BaseModel

from nexus_core import paths, runner, services
from nexus_core.errors import ValidationError
from nexus_core.gateway import certs
from nexus_core.gateway.model import Route, load_routes


class GatewayStatus(BaseModel):
    nginx_installed: bool
    nginx_state: str
    routes_total: int
    routes_active: int
    routes_pending: int
    last_applied: float | None = None
    certificates_expiring: int = 0


class BackendCheck(BaseModel):
    route: str
    url: str
    ok: bool
    status_code: int | None = None
    latency_ms: float | None = None
    error: str | None = None


def gateway_dir() -> Path:
    return paths.gateway_dir()


def routes() -> list[Route]:
    return load_routes(gateway_dir() / "routes")


def status() -> GatewayStatus:
    import json

    gdir = gateway_dir()
    all_routes = routes()
    state = gdir / "state.json"
    last = None
    if state.exists():
        try:
            last = json.loads(state.read_text()).get("applied_at")
        except ValueError:
            last = None
    try:
        expiring = sum(1 for c in certs.inventory(gdir) if c.status != "ok")
    except Exception:
        expiring = 0
    return GatewayStatus(
        nginx_installed=runner.which("nginx") is not None or Path("/usr/sbin/nginx").exists(),
        nginx_state=services.is_active("nginx.service"),
        routes_total=len(all_routes),
        routes_active=sum(1 for r in all_routes if r.enabled and r.approved),
        routes_pending=sum(1 for r in all_routes if not r.approved),
        last_applied=last,
        certificates_expiring=expiring,
    )


def test_backend(route: Route, transport: httpx.BaseTransport | None = None) -> BackendCheck:
    host = route.backend_host if ":" not in route.backend_host else f"[{route.backend_host}]"
    url = f"{route.backend_scheme}://{host}:{route.backend_port}{route.path_prefix}"
    try:
        route.check_backend()
    except ValidationError as exc:
        return BackendCheck(route=route.id, url=url, ok=False, error=exc.message)
    start = time.monotonic()
    try:
        with httpx.Client(timeout=5, verify=False, transport=transport, follow_redirects=False) as client:  # noqa: S501 - backends often use internal certs
            response = client.get(url)
        return BackendCheck(
            route=route.id,
            url=url,
            ok=response.status_code < 500,
            status_code=response.status_code,
            latency_ms=round((time.monotonic() - start) * 1000, 1),
        )
    except httpx.HTTPError as exc:
        return BackendCheck(route=route.id, url=url, ok=False, error=exc.__class__.__name__)
