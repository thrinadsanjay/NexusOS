"""``nexus network`` -- NetworkManager status, interfaces, DNS and diagnostics."""

from __future__ import annotations

import typer
from nexus_core import network as net

from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.output import console, print_json, table

app = typer.Typer(help="Networking (NetworkManager).", no_args_is_help=True)


@app.command("status")
@handle_errors
def status(json_output: bool = typer.Option(False, "--json")) -> None:
    """Connectivity and active connections."""
    data = {"connectivity": net.connectivity(), "connections": [c.model_dump() for c in net.connections() if c.active]}
    if json_output:
        print_json(data)
        return
    console.print(f"connectivity: [accent]{data['connectivity']}[/accent]")
    table(
        "Active connections",
        ["Name", "Type", "Device"],
        [[c["name"], c["type"], c["device"]] for c in data["connections"]],
    )


@app.command("interfaces")
@handle_errors
def interfaces(json_output: bool = typer.Option(False, "--json")) -> None:
    """Network devices and addresses."""
    devs = net.devices()
    if json_output:
        print_json(devs)
        return
    table(
        "Interfaces",
        ["Device", "Type", "State", "Connection", "Addresses"],
        [[d.name, d.type, d.state, d.connection, ", ".join(d.addresses)] for d in devs],
    )


@app.command("routes")
@handle_errors
def routes() -> None:
    """Routing table."""
    table(
        "Routes",
        ["Destination", "Gateway", "Device", "Protocol"],
        [[r.get("dst"), r.get("gateway"), r.get("dev"), r.get("protocol")] for r in net.routes()],
    )


@app.command("dns")
@handle_errors
def dns() -> None:
    """DNS servers per link."""
    table("DNS", ["Link", "Servers"], [[k, ", ".join(v)] for k, v in net.dns().items()])


@app.command("diagnostics")
@handle_errors
def diagnostics(target: str = typer.Argument("archive.ubuntu.com")) -> None:
    """DNS, ping, route and tracepath to a target."""
    for r in net.diagnose(target):
        console.print(f"[accent]== {r.tool}[/accent] {'ok' if r.ok else 'failed'}")
        console.print(r.output, markup=False, highlight=False)


@app.command("firewall")
@handle_errors
def firewall() -> None:
    """Firewall (ufw) status via the management agent."""
    console.print(net.firewall_status().get("output", ""), markup=False, highlight=False)
