"""``nexus containers`` -- Docker Engine through the local socket API."""

from __future__ import annotations

import json

import typer
from nexus_core import activity
from nexus_core import docker as engine
from nexus_core.errors import AbortedError

from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.output import confirm, console, print_json, table

app = typer.Typer(help="Docker containers, images, volumes and networks.", no_args_is_help=True)


@app.command("list")
@handle_errors
def list_cmd(
    running: bool = typer.Option(False, "--running"), json_output: bool = typer.Option(False, "--json")
) -> None:
    """List containers."""
    with engine.DockerClient() as c:
        items = [x for x in c.containers() if not running or x.state == "running"]
    if json_output:
        print_json(items)
        return
    table(
        "Containers",
        ["Name", "Image", "State", "Status", "Ports"],
        [[x.name, x.image, x.state, x.status, ", ".join(x.ports)] for x in items],
    )


def _action(name: str, action: str) -> None:
    with engine.DockerClient() as c:
        c.container_action(name, action)
    activity.record(f"container.{action}", name, "ok")
    console.print(f"[ok]{name}: {action}[/ok]")


@app.command("start")
@handle_errors
def start(name: str) -> None:
    """Start a container."""
    _action(name, "start")


@app.command("stop")
@handle_errors
def stop(name: str) -> None:
    """Stop a container."""
    _action(name, "stop")


@app.command("restart")
@handle_errors
def restart(name: str) -> None:
    """Restart a container."""
    _action(name, "restart")


@app.command("rm")
@handle_errors
def rm(name: str, force: bool = False) -> None:
    """Remove a container (asks first)."""
    if not confirm(f"Remove container {name}?"):
        raise AbortedError("cancelled")
    with engine.DockerClient() as c:
        c.remove_container(name, force=force)


@app.command("logs")
@handle_errors
def logs(name: str, tail: int = 200) -> None:
    """Container logs (secrets redacted)."""
    with engine.DockerClient() as c:
        console.print(c.logs(name, tail), markup=False, highlight=False)


@app.command("inspect")
@handle_errors
def inspect(name: str) -> None:
    """Inspect a container (environment values redacted)."""
    with engine.DockerClient() as c:
        console.print(json.dumps(c.inspect_container(name), indent=2), markup=False, highlight=False)


@app.command("stats")
@handle_errors
def stats(name: str) -> None:
    """One-shot CPU/memory usage."""
    with engine.DockerClient() as c:
        print_json(c.stats(name))


@app.command("images")
@handle_errors
def images() -> None:
    """List images."""
    with engine.DockerClient() as c:
        table("Images", ["Tags", "ID", "Size"], [[", ".join(i["tags"]), i["id"], i["size"]] for i in c.images()])


@app.command("pull")
@handle_errors
def pull(reference: str) -> None:
    """Pull an image."""
    with engine.DockerClient() as c:
        for event in c.pull(reference):
            console.print(f"{event.get('status', '')} {event.get('progress', '')}", markup=False, highlight=False)


@app.command("volumes")
@handle_errors
def volumes() -> None:
    """List volumes."""
    with engine.DockerClient() as c:
        table(
            "Volumes",
            ["Name", "Driver", "Mountpoint"],
            [[v["name"], v["driver"], v["mountpoint"]] for v in c.volumes()],
        )


@app.command("networks")
@handle_errors
def networks() -> None:
    """List networks."""
    with engine.DockerClient() as c:
        table("Networks", ["Name", "Driver", "Scope"], [[n["name"], n["driver"], n["scope"]] for n in c.networks()])


@app.command("compose")
@handle_errors
def compose_projects() -> None:
    """Discovered Compose projects."""
    with engine.DockerClient() as c:
        table(
            "Compose projects",
            ["Project", "Running", "Directory"],
            [[p["name"], f"{p['running']}/{p['total']}", p["working_dir"]] for p in c.compose_projects()],
        )
