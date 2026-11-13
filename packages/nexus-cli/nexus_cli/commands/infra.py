"""``nexus infra`` -- containers and virtualisation."""

from __future__ import annotations

import typer
from nexus_core import docker as docker_service
from nexus_core import tools
from nexus_core.errors import DependencyMissingError
from nexus_core.models import ToolInfo
from rich.table import Table

from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.output import console, print_json, status_text

app = typer.Typer(help="Containers and virtualisation.", no_args_is_help=True)

PODMAN = tools.ToolSpec("Podman", "podman", ("--version",))


@app.command("status")
@handle_errors
def status(json_output: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Summarise Docker, KVM, libvirt and Podman availability."""
    docker = docker_service.docker_status(include_containers=True)
    kvm = tools.kvm_status()
    libvirt = tools.libvirt_status()
    podman = tools.probe(PODMAN)
    groups = sorted(tools.user_groups() & {"docker", "kvm", "libvirt"})
    if json_output:
        print_json(
            {
                "docker": docker.model_dump(exclude={"containers"})
                | {
                    "containers_total": len(docker.containers),
                    "containers_running": sum(c.state == "running" for c in docker.containers),
                },
                "kvm": kvm.model_dump(),
                "libvirt": libvirt.model_dump(),
                "podman": podman.model_dump(),
                "groups": groups,
            }
        )
        return

    table = Table(title="Infrastructure", title_style="accent", header_style="muted")
    table.add_column("Component")
    table.add_column("Status", no_wrap=True)
    table.add_column("Detail")
    if docker.reachable:
        running = sum(c.state == "running" for c in docker.containers)
        table.add_row(
            "Docker Engine",
            status_text("ok"),
            f"{docker.server_version}, {running}/{len(docker.containers)} containers running",
        )
    else:
        table.add_row(
            "Docker Engine", status_text("warn" if docker.cli_installed else "skip"), _detail(docker.error, docker.hint)
        )
    for item in (kvm, libvirt, podman):
        table.add_row(item.name, status_text("ok" if item.available else "skip"), _tool_detail(item))
    console.print(table)
    console.print(f"[muted]Groups:[/muted] {', '.join(groups) if groups else 'none of docker/kvm/libvirt'}")


def _detail(error: str | None, hint: str | None) -> str:
    return (error or "") + (f"\n[muted]{hint}[/muted]" if hint else "")


def _tool_detail(item: ToolInfo) -> str:
    parts = [p for p in (item.version, item.note) if p]
    return " - ".join(parts) if parts else ("available" if item.available else "not installed")


@app.command("containers")
@handle_errors
def containers(
    all_containers: bool = typer.Option(True, "--all/--running", help="Include stopped containers."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """List Docker containers through the Engine API (read-only)."""
    docker = docker_service.docker_status(include_containers=True)
    if not docker.reachable:
        raise DependencyMissingError(docker.error or "Docker Engine unavailable", hint=docker.hint)
    items = docker.containers if all_containers else [c for c in docker.containers if c.state == "running"]
    if json_output:
        print_json(items)
        return
    if not items:
        console.print(f"[muted]Docker {docker.server_version}: no containers.[/muted]")
        return
    table = Table(title=f"Docker {docker.server_version} containers", title_style="accent", header_style="muted")
    for column in ("Name", "Image", "State", "Status", "Ports", "ID"):
        table.add_column(column)
    for c in items:
        state = f"[ok]{c.state}[/ok]" if c.state == "running" else f"[muted]{c.state}[/muted]"
        table.add_row(c.name, c.image, state, c.status, ", ".join(c.ports), f"[muted]{c.id}[/muted]")
    console.print(table)
