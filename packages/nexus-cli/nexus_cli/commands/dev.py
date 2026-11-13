"""``nexus dev`` -- development templates and toolchain detection."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from nexus_cli.core import runner
from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.errors import AbortedError, NexusError
from nexus_cli.core.output import confirm, console, print_json
from nexus_cli.services import scaffold, tools

app = typer.Typer(help="Development templates and toolchains.", no_args_is_help=True)
create_app = typer.Typer(help="Create a new project from a template.", no_args_is_help=True)
app.add_typer(create_app, name="create")

PATH_OPTION = typer.Option(Path("."), "--path", "-p", help="Parent directory for the new project.")


@app.command("list")
@handle_errors
def list_templates(json_output: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """List project templates and detected development toolchains."""
    toolchains = tools.probe_all(tools.DEV_TOOLS)
    if json_output:
        print_json(
            {
                "templates": [t.__dict__ | {"requires": list(t.requires)} for t in scaffold.TEMPLATES],
                "toolchains": [t.model_dump() for t in toolchains],
            }
        )
        return
    table = Table(title="Templates  (nexus dev create <template> NAME)", title_style="accent", header_style="muted")
    table.add_column("Template", style="accent")
    table.add_column("Description")
    table.add_column("Requires", style="muted")
    table.add_column("Offline", justify="center")
    for template in scaffold.TEMPLATES:
        table.add_row(
            template.name, template.description, ", ".join(template.requires), "yes" if template.offline else "no"
        )
    console.print(table)

    tc = Table(title="Toolchains", title_style="accent", header_style="muted")
    tc.add_column("Tool")
    tc.add_column("Version")
    for tool in toolchains:
        tc.add_row(
            tool.name, f"[ok]{tool.version or 'installed'}[/ok]" if tool.available else "[muted]not installed[/muted]"
        )
    console.print(tc)


@create_app.command("fastapi")
@handle_errors
def create_fastapi(
    name: str = typer.Argument(..., help="Project name (lowercase, digits, '-' or '_')."),
    path: Path = PATH_OPTION,
) -> None:
    """Generate a working FastAPI project (no network access required)."""
    target, files = scaffold.create_fastapi_project(name, path)
    console.print(f"[ok]Created[/ok] {target}")
    for rel in files:
        console.print(f"  [muted]+[/muted] {rel}")
    console.print(
        "\nNext steps:\n"
        f"  cd {target}\n"
        "  python3 -m venv .venv && . .venv/bin/activate\n"
        "  pip install -r requirements-dev.txt\n"
        "  pytest && uvicorn app.main:app --reload"
    )


@create_app.command("react")
@handle_errors
def create_react(
    name: str = typer.Argument(..., help="Project name (lowercase, digits, '-' or '_')."),
    path: Path = PATH_OPTION,
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the scaffolding command without running it."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask before downloading create-vite from npm."),
) -> None:
    """Scaffold a React + TypeScript app with Vite (the method documented by react.dev and vite.dev)."""
    command = scaffold.react_command(name)
    target = scaffold.prepare_target(path, name)
    console.print(f"[muted]Will run in {target.parent}:[/muted] {' '.join(command)}")
    if dry_run:
        return
    node_version = scaffold.check_node()
    console.print(f"[muted]Node.js {node_version} detected. This downloads create-vite from the npm registry.[/muted]")
    if not yes and not confirm("Continue?", default=True):
        raise AbortedError("cancelled")
    code = runner.run_interactive(command, cwd=target.parent)
    if code != 0:
        raise NexusError(f"npm create vite exited with status {code}")
    console.print(f"\n[ok]Created[/ok] {target}\nNext steps:\n  cd {target}\n  npm install\n  npm run dev")
