"""``nexus profiles`` -- installation profiles (nothing optional is installed automatically)."""

from __future__ import annotations

import typer
from nexus_core import packages as pk
from nexus_core import profiles as pr

from nexus_cli.commands.packages import _execute, _show_plan
from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.output import console, table

app = typer.Typer(help="Installation profiles.", no_args_is_help=True)


@app.command("list")
@handle_errors
def list_cmd() -> None:
    """Available profiles."""
    table("Profiles", ["Id", "Name", "Description"], [[p.id, p.name, p.description] for p in pr.load()])


@app.command("show")
@handle_errors
def show(profile_id: str) -> None:
    """Packages and applications a profile would add."""
    p = pr.get(profile_id)
    console.print(f"[accent]{p.name}[/accent]: {p.description}")
    console.print("packages: " + " ".join(pr.packages_for(p)), markup=False)
    console.print("applications (install separately): " + (", ".join(p.applications) or "none"))
    if p.external:
        console.print("external (opt-in, see docs/installation.md): " + ", ".join(p.external))


@app.command("apply")
@handle_errors
def apply(profile_id: str, yes: bool = typer.Option(False, "--yes", "-y")) -> None:
    """Install a profile's packages (plan shown first). Applications are installed with `nexus apps install`."""
    plan = pk.plan("install", pr.packages_for(pr.get(profile_id)))
    _show_plan(plan)
    _execute(plan, yes)
