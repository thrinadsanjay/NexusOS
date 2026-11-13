"""``nexus cloud`` -- cloud and Kubernetes tooling status."""

from __future__ import annotations

import typer
from rich.table import Table

from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.output import console, print_json
from nexus_cli.services import tools

app = typer.Typer(help="Cloud and Kubernetes tooling.", no_args_is_help=True)


@app.command("status")
@handle_errors
def status(json_output: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Detect cloud CLIs and whether they are configured. Never prints credentials."""
    results = tools.probe_all(tools.CLOUD_TOOLS)
    configured = {t.name: tools.cloud_config_present(t.name) for t in results}
    context = tools.kube_current_context()
    if json_output:
        print_json(
            {
                "tools": [t.model_dump() | {"configured": configured[t.name]} for t in results],
                "kubernetes_context": context,
            }
        )
        return
    table = Table(title="Cloud tooling", title_style="accent", header_style="muted")
    table.add_column("Tool")
    table.add_column("Version")
    table.add_column("Config found", justify="center")
    for tool in results:
        version = f"[ok]{tool.version or 'installed'}[/ok]" if tool.available else "[muted]not installed[/muted]"
        has_config = "yes" if configured[tool.name] else "[muted]-[/muted]"
        table.add_row(tool.name, version, has_config if tool.available else "[muted]-[/muted]")
    console.print(table)
    if context:
        console.print(f"Kubernetes context: [accent]{context}[/accent]")
    if not any(t.available for t in results):
        console.print(
            "[muted]No cloud CLIs found. Cloud tooling is not part of the base image; see docs/installation.md.[/muted]"
        )
