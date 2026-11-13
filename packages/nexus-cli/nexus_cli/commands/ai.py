"""``nexus ai`` -- local AI (Ollama) status and models."""

from __future__ import annotations

import httpx
import typer
from nexus_core import chat, ollama
from nexus_core.errors import DependencyMissingError
from nexus_core.system import human_bytes
from rich.table import Table

from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.output import console, print_json, status_text

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


@app.command("pull")
@handle_errors
def pull(model: str) -> None:
    """Download a model (explicit user action only)."""
    for event in ollama.pull(model):
        total, done = event.get("total") or 0, event.get("completed") or 0
        pct = f" {100 * done / total:5.1f}%" if total else ""
        console.print(f"{event.get('status', '')}{pct}", markup=False, highlight=False)


@app.command("rm")
@handle_errors
def rm(model: str) -> None:
    """Delete a local model."""
    from nexus_cli.core.output import confirm

    if confirm(f"Delete model {model}?"):
        ollama.delete(model)


@app.command("ps")
@handle_errors
def ps() -> None:
    """Models currently loaded, with RAM/VRAM and CPU/GPU mode."""
    from nexus_cli.core.output import table

    rows = [[m.name, human_bytes(m.size_bytes), human_bytes(m.vram_bytes), m.mode] for m in ollama.running()]
    table("Loaded models", ["Model", "Size", "VRAM", "Mode"], rows)
    print_json(ollama.gpu_inference_support())


@app.command("chat")
@handle_errors
def chat_cmd(
    model: str = typer.Argument(..., help="installed model, e.g. llama3.2:3b"),
    prompt: str | None = typer.Option(None, "--prompt", "-p", help="One-shot prompt (otherwise interactive)."),
    system: str = typer.Option("", help="System prompt."),
) -> None:
    """Chat with a local model (streaming). Conversations are saved locally; Ctrl+C stops generation."""
    import threading

    cid = chat.create(model, system)
    stop = threading.Event()

    def ask(text: str) -> None:
        chat.add_message(cid, "user", text)
        parts: list[str] = []
        try:
            for chunk in ollama.chat_stream(model, chat.context(cid), cancel=stop):
                parts.append(chunk)
                console.print(chunk, end="", markup=False, highlight=False)
        except KeyboardInterrupt:
            stop.set()
            console.print("\n[muted](stopped)[/muted]")
        console.print()
        chat.add_message(cid, "assistant", "".join(parts))
        stop.clear()

    if prompt:
        ask(prompt)
        return
    console.print(f"[muted]Chatting with {model}. Empty line or Ctrl+D to quit.[/muted]")
    while True:
        try:
            text = console.input("[accent]> [/accent]")
        except (EOFError, KeyboardInterrupt):
            break
        if not text.strip():
            break
        ask(text)
