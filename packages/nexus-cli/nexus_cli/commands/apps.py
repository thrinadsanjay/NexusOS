"""``nexus apps`` -- Nexus application registry and lifecycle (Docker Compose)."""

from __future__ import annotations

from pathlib import Path

import typer
from nexus_core import activity, agent_client
from nexus_core.apps import lifecycle, registry
from nexus_core.errors import AbortedError

from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.output import confirm, console, print_json, run_agent, table

app = typer.Typer(help="Optional Nexus applications.", no_args_is_help=True)


@app.command("list")
@handle_errors
def list_cmd(json_output: bool = typer.Option(False, "--json")) -> None:
    """Application catalogue with install state."""
    items = lifecycle.catalog()
    if json_output:
        print_json([{"app": a.model_dump(), "state": s.model_dump()} for a, s in items])
        return
    table(
        "Nexus applications",
        ["Id", "Name", "Status", "Installed", "Version"],
        [[a.id, a.name, a.status, s.status if s.installed else "no", a.version] for a, s in items],
    )


@app.command("status")
@handle_errors
def status(app_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    """Status, health, services and URLs of one application."""
    st = lifecycle.status(app_id)
    if json_output:
        print_json(st)
        return
    a = registry.get(app_id)
    console.print(f"[accent]{a.name}[/accent] {a.version} -- {a.status}: {a.status_reason or a.summary}")
    if not st.installed:
        problems = lifecycle.check_dependencies(a)
        console.print("not installed" + ("; blocked by: " + "; ".join(problems) if problems else ""))
        return
    table("Services", ["Service", "State", "Health"], [[s["name"], s["state"], s["health"]] for s in st.services])
    console.print(f"health: {st.health}  urls: {', '.join(st.urls)}")


@app.command("install")
@handle_errors
def install(
    app_id: str,
    set_value: list[str] = typer.Option([], "--set", help="KEY=VALUE configuration override"),
    yes: bool = typer.Option(False, "--yes", "-y"),
    propose_route: bool = typer.Option(True),
) -> None:
    """Install an application (fetches the pinned version, generates secrets, loopback-only ports)."""
    a = registry.get(app_id)
    console.print(f"{a.name} {a.version}: {a.summary}")
    if a.deployment and a.deployment.source_repo:
        console.print(f"source {a.deployment.source_repo} @ {a.deployment.source_ref}")
    if not yes and not confirm(f"Install {a.name}?"):
        raise AbortedError("cancelled")
    overrides = dict(v.split("=", 1) for v in set_value)
    st = lifecycle.install(app_id, overrides)
    activity.record("apps.install", app_id, "ok")
    console.print(f"[ok]installed[/ok] status={st.status} urls={', '.join(st.urls)}")
    route = lifecycle.suggested_route(a)
    if propose_route and route and agent_client.available():
        run_agent("gateway.route.save", {"route": route})
        console.print(
            f"gateway route {route['hostname']} proposed (pending approval: nexus gateway routes approve {app_id})"
        )


def _verb(app_id: str, verb: str) -> None:
    lifecycle.action(app_id, verb)
    activity.record(f"apps.{verb}", app_id, "ok")
    console.print(f"[ok]{app_id}: {verb}[/ok]")


@app.command("start")
@handle_errors
def start(app_id: str) -> None:
    """Start an installed application."""
    _verb(app_id, "start")


@app.command("stop")
@handle_errors
def stop(app_id: str) -> None:
    """Stop an installed application."""
    _verb(app_id, "stop")


@app.command("restart")
@handle_errors
def restart(app_id: str) -> None:
    """Restart an installed application."""
    _verb(app_id, "restart")


@app.command("logs")
@handle_errors
def logs(app_id: str, tail: int = 200) -> None:
    """Application logs (secrets redacted)."""
    console.print(lifecycle.logs(app_id, tail), markup=False, highlight=False)


@app.command("update")
@handle_errors
def update(app_id: str) -> None:
    """Re-deploy at the version pinned in the registry."""
    st = lifecycle.update(app_id)
    console.print(f"[ok]updated[/ok] {st.version} ({st.status})")


@app.command("uninstall")
@handle_errors
def uninstall(
    app_id: str, delete_data: bool = typer.Option(False, "--delete-data", help="Also delete volumes and config.")
) -> None:
    """Uninstall an application (data kept unless --delete-data)."""
    if not confirm(f"Uninstall {app_id}{' AND DELETE ITS DATA' if delete_data else ''}?"):
        raise AbortedError("cancelled")
    lifecycle.uninstall(app_id, delete_data)
    activity.record("apps.uninstall", app_id, "ok")


@app.command("backup")
@handle_errors
def backup(app_id: str, destination: Path | None = typer.Option(None, help="Default: ~/NexusOS-Backups")) -> None:
    """Back up configuration and data volumes to a tar.gz (mode 600)."""
    path = lifecycle.backup(app_id, destination or Path.home() / "NexusOS-Backups")
    console.print(f"[ok]backup written:[/ok] {path}")


@app.command("restore")
@handle_errors
def restore(app_id: str, archive: Path) -> None:
    """Restore from a backup (overwrites data)."""
    if not confirm(f"Restore {app_id} from {archive}? Current data is overwritten."):
        raise AbortedError("cancelled")
    lifecycle.restore(app_id, archive, confirmed=True)
