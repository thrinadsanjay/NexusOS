"""Entry point for the ``nexus`` command."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

import typer
from nexus_core.errors import ValidationError
from nexus_core.models import VersionInfo
from nexus_core.release import creator, read_nexusos_release, read_os_release

from nexus_cli import __version__
from nexus_cli.commands import (
    ai,
    apps,
    cloud,
    containers,
    dev,
    gateway,
    infra,
    network,
    packages,
    profiles,
    ssh,
    storage,
    system,
)
from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.logging import configure_logging, get_logger
from nexus_cli.core.output import console, err_console, print_json

app = typer.Typer(
    name="nexus",
    help="NexusOS Engineering Edition toolkit.  BUILD. AUTOMATE. DEPLOY.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(system.app, name="system")
app.add_typer(dev.app, name="dev")
app.add_typer(cloud.app, name="cloud")
app.add_typer(infra.app, name="infra")
app.add_typer(ai.app, name="ai")
app.add_typer(packages.app, name="packages")
app.add_typer(ssh.app, name="ssh")
app.add_typer(containers.app, name="containers")
app.add_typer(apps.app, name="apps")
app.add_typer(gateway.app, name="gateway")
app.add_typer(storage.app, name="storage")
app.add_typer(network.app, name="network")
app.add_typer(profiles.app, name="profiles")


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging on stderr."),
    log_file: Path | None = typer.Option(None, "--log-file", help="Also write debug logs to this file."),
) -> None:
    """NexusOS Engineering Edition toolkit."""
    configure_logging(verbose=verbose, log_file=log_file)


@app.command("version")
@handle_errors
def version(json_output: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Show the NexusOS CLI version and platform details."""
    os_release = read_os_release()
    release = read_nexusos_release()
    info = VersionInfo(
        cli_version=__version__,
        python_version=platform.python_version(),
        os=os_release,
        nexusos_build=release.get("NEXUSOS_BUILD"),
        creator=creator(),
    )
    if json_output:
        print_json(info)
        return
    console.print(f"[accent]nexus[/accent] {info.cli_version}  [muted]NexusOS CLI[/muted]")
    console.print(
        f"[muted]OS:[/muted] {os_release.pretty_name}"
        + (f" [muted](build {info.nexusos_build})[/muted]" if info.nexusos_build else "")
    )
    console.print(f"[muted]Python:[/muted] {info.python_version}")
    if info.creator:
        console.print(f"[muted]Crafted by[/muted] [accent]{info.creator}[/accent]")


@app.command("help")
@handle_errors
def help_command(
    ctx: typer.Context,
    group: str | None = typer.Argument(None, help="Command group to describe, e.g. 'system'."),
) -> None:
    """Show help for all commands, or for one command group."""
    root_ctx = ctx.find_root()
    root_cmd = root_ctx.command
    if group is None:
        typer.echo(root_cmd.get_help(root_ctx))
        return
    # Duck-typed: Typer releases differ in whether they vendor Click.
    get_command = getattr(root_cmd, "get_command", None)
    sub = get_command(root_ctx, group) if get_command else None
    if sub is None:
        raise ValidationError(f"unknown command group {group!r}", hint="run `nexus help` to list groups")
    with root_ctx.__class__(sub, info_name=group, parent=root_ctx) as sub_ctx:
        typer.echo(sub.get_help(sub_ctx))


def run() -> None:
    """Console-script entry point with a last-resort error handler."""
    try:
        app()
    except KeyboardInterrupt:
        err_console.print("[muted]interrupted[/muted]")
        sys.exit(130)
    except Exception as exc:  # pragma: no cover - defensive
        get_logger("main").debug("unhandled exception", exc_info=True)
        err_console.print(f"[fail]unexpected error:[/fail] {exc.__class__.__name__}: {exc}")
        err_console.print("[muted]re-run with --verbose for details[/muted]")
        sys.exit(70)


__all__ = ["app", "print_json", "run"]
