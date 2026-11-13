"""``nexus ai`` -- local AI (Ollama) status and models."""

from __future__ import annotations

import httpx
import typer
from rich.table import Table

from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.errors import DependencyMissingError
from nexus_cli.core.output import console, print_json, status_text
from nexus_cli.services import ollama
from nexus_cli.services.system import human_bytes

app = typer.Typer(help="Local AI inference (Ollama).", no_args_is_help=True)


@app.command("status")
@handle_errors
def status(json_output: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Detect whether Ollama is installed and its API is reachable. Exits 3 if unreachable."""
    result = ollama.ollama_status()
    if json_output:
        print_json(result)
    else:
        if result.reachable:
            console.print(f"{status_text('ok')} Ollama {result.version} at {result.endpoint}")
        else:
            console.print(f"{status_text('skip')} {result.error} [muted]({result.endpoint})[/muted]")
            console.print(f"[muted]CLI installed: {'yes' if result.cli_installed else 'no'}[/muted]")
            if result.hint:
                console.print(f"[muted]hint: {result.hint}[/muted]")
    if not result.reachable:
        raise typer.Exit(DependencyMissingError.exit_code)


@app.command("models")
@handle_errors
def models(json_output: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """List models installed in the local Ollama instance. Never downloads models."""
    endpoint = ollama.resolve_endpoint()
    try:
        items = ollama.list_models(endpoint)
    except httpx.ConnectError:
        raise DependencyMissingError(f"Ollama is not reachable at {endpoint}", hint="check `nexus ai status`") from None
    except (httpx.HTTPError, ValueError) as exc:
        raise DependencyMissingError(f"Ollama API error: {exc.__class__.__name__}") from None
    if json_output:
        print_json(items)
        return
    if not items:
        console.print("[muted]No local models. Pull one explicitly, e.g. `ollama pull llama3.2:3b`.[/muted]")
        return
    table = Table(title="Local Ollama models", title_style="accent", header_style="muted")
    for column in ("Model", "Size", "Parameters", "Quantisation", "Modified"):
        table.add_column(column)
    for m in items:
        modified = m.modified_at.strftime("%Y-%m-%d") if m.modified_at else ""
        table.add_row(m.name, human_bytes(m.size_bytes), m.parameter_size or "", m.quantization or "", modified)
    console.print(table)
