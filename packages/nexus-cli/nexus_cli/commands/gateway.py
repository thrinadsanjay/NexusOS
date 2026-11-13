"""``nexus gateway`` -- native NGINX gateway (reads unprivileged, writes through the agent)."""

from __future__ import annotations

import typer
from nexus_core import paths
from nexus_core.errors import AbortedError, NexusError
from nexus_core.gateway import certs, status
from nexus_core.gateway.model import Route

from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.output import confirm, console, print_json, run_agent, table

app = typer.Typer(help="Gateway routes, certificates and NGINX.", no_args_is_help=True)
routes_app = typer.Typer(help="Declarative routes.", no_args_is_help=True)
ssl_app = typer.Typer(help="Certificates.", no_args_is_help=True)
nginx_app = typer.Typer(help="NGINX service.", no_args_is_help=True)
app.add_typer(routes_app, name="routes")
app.add_typer(ssl_app, name="ssl")
app.add_typer(nginx_app, name="nginx")


@app.command("status")
@handle_errors
def status_cmd(json_output: bool = typer.Option(False, "--json")) -> None:
    """NGINX state, route counts, certificate warnings."""
    st = status.status()
    if json_output:
        print_json(st)
        return
    table(
        "Gateway",
        ["Item", "Value"],
        [
            ["NGINX installed", st.nginx_installed],
            ["NGINX", st.nginx_state],
            ["Active routes", st.routes_active],
            ["Pending approval", st.routes_pending],
            ["Certificates needing attention", st.certificates_expiring],
        ],
    )


@app.command("apply")
@handle_errors
def apply_cmd(yes: bool = typer.Option(False, "--yes", "-y")) -> None:
    """Render approved routes, test with nginx -t, reload, roll back on failure."""
    if not yes and not confirm("Apply gateway configuration?"):
        raise AbortedError("cancelled")
    result = run_agent("gateway.apply")
    console.print(result.get("message", ""), markup=False)
    if result.get("nginx_output"):
        console.print(result["nginx_output"], markup=False, highlight=False)
    if not result.get("ok"):
        raise NexusError("gateway activation failed (previous configuration restored)")


@app.command("rollback")
@handle_errors
def rollback() -> None:
    """Restore the most recent configuration backup."""
    if confirm("Roll back to the last backup?"):
        console.print(run_agent("gateway.rollback").get("message", ""))


@routes_app.command("list")
@handle_errors
def routes_list(json_output: bool = typer.Option(False, "--json")) -> None:
    """List routes."""
    items = status.routes()
    if json_output:
        print_json(items)
        return
    table(
        "Routes",
        ["Id", "Hostname", "Backend", "TLS", "Access", "State"],
        [
            [
                r.id,
                r.hostname + (r.path_prefix if r.path_prefix != "/" else ""),
                f"{r.backend_scheme}://{r.backend_host}:{r.backend_port}",
                r.tls,
                r.access,
                "pending" if not r.approved else ("enabled" if r.enabled else "disabled"),
            ]
            for r in items
        ],
    )


@routes_app.command("add")
@handle_errors
def routes_add(
    route_id: str,
    hostname: str,
    backend_port: int,
    backend_host: str = "127.0.0.1",
    backend_scheme: str = "http",
    path: str = "/",
    tls: str = "internal-ca",
    certificate: str | None = None,
    access: str = "lan",
    websocket: bool = False,
    approve: bool = typer.Option(False, "--approve", help="Approve immediately (still needs apply)."),
) -> None:
    """Create or replace a route (validated, SSRF-checked)."""
    route = Route(
        id=route_id,
        hostname=hostname,
        backend_host=backend_host,
        backend_port=backend_port,
        backend_scheme=backend_scheme,
        path_prefix=path,
        tls=tls,
        certificate=certificate,
        access=access,
        websocket=websocket,
        approved=approve,
    )
    route.check_backend()
    if access == "public" and not confirm(
        "Public access exposes this application to everyone who can reach the host. Continue?"
    ):
        raise AbortedError("cancelled")
    run_agent("gateway.route.save", {"route": route.model_dump()})
    console.print(f"[ok]saved {route_id}[/ok] -- run `nexus gateway apply` to activate")


@routes_app.command("approve")
@handle_errors
def routes_approve(route_id: str) -> None:
    """Approve a pending route (e.g. one proposed by an application install)."""
    route = next((r for r in status.routes() if r.id == route_id), None)
    if route is None:
        raise NexusError(f"no route {route_id}")
    console.print(
        f"{route.hostname} -> {route.backend_host}:{route.backend_port}  tls={route.tls} access={route.access}"
    )
    if confirm("Approve this route?"):
        run_agent("gateway.route.save", {"route": {**route.model_dump(), "approved": True}})


@routes_app.command("remove")
@handle_errors
def routes_remove(route_id: str) -> None:
    """Delete a route."""
    if confirm(f"Delete route {route_id}?"):
        run_agent("gateway.route.delete", {"id": route_id})


@routes_app.command("test")
@handle_errors
def routes_test(route_id: str | None = typer.Argument(None)) -> None:
    """Test backend connectivity of one or all routes (SSRF-safe)."""
    items = [r for r in status.routes() if route_id in (None, r.id)]
    checks = [status.test_backend(r) for r in items]
    table(
        "Backend checks",
        ["Route", "URL", "OK", "Status", "Latency ms", "Error"],
        [[c.route, c.url, c.ok, c.status_code, c.latency_ms, c.error] for c in checks],
    )


@ssl_app.command("list")
@handle_errors
def ssl_list(json_output: bool = typer.Option(False, "--json")) -> None:
    """Certificate inventory."""
    items = certs.inventory(paths.gateway_dir())
    if json_output:
        print_json(items)
        return
    table(
        "Certificates",
        ["Name", "Source", "Names", "Expires", "Days", "Status"],
        [[c.name, c.source, ", ".join(c.sans), c.not_after[:10], c.days_left, c.status] for c in items],
    )


@ssl_app.command("status")
@handle_errors
def ssl_status() -> None:
    """Certificates that expire soon or have expired."""
    due = [c for c in certs.inventory(paths.gateway_dir()) if c.status != "ok"]
    if not due:
        console.print("[ok]all certificates valid for 30+ days[/ok]")
        return
    table("Attention", ["Name", "Days left", "Status"], [[c.name, c.days_left, c.status] for c in due])


@ssl_app.command("issue")
@handle_errors
def ssl_issue(
    name: str,
    hostnames: list[str],
    mode: str = typer.Option("internal-ca", help="internal-ca | self-signed | letsencrypt"),
    email: str | None = None,
    staging: bool = False,
) -> None:
    """Issue a certificate."""
    run_agent(
        "gateway.cert.issue", {"mode": mode, "name": name, "hostnames": hostnames, "email": email, "staging": staging}
    )


@ssl_app.command("renew")
@handle_errors
def ssl_renew() -> None:
    """Re-issue internal/self-signed certificates expiring within 30 days."""
    print_json(run_agent("gateway.cert.renew"))


@nginx_app.command("test")
@handle_errors
def nginx_test() -> None:
    """Run nginx -t."""
    result = run_agent("gateway.nginx.test")
    console.print(result.get("output", ""), markup=False)
    if not result.get("ok"):
        raise NexusError("nginx configuration test failed")


@nginx_app.command("reload")
@handle_errors
def nginx_reload() -> None:
    """Reload NGINX (only if nginx -t passes)."""
    result = run_agent("gateway.nginx.reload")
    if not result.get("ok"):
        raise NexusError(result.get("message") or "reload failed", hint=result.get("output"))
    console.print("[ok]reloaded[/ok]")


@nginx_app.command("logs")
@handle_errors
def nginx_logs(kind: str = typer.Argument("error"), lines: int = 100) -> None:
    """Gateway access/error logs (administrators)."""
    for line in run_agent("gateway.logs", {"kind": kind, "lines": lines}).get("lines", []):
        console.print(line, markup=False, highlight=False)
