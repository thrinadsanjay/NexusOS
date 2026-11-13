"""``nexus packages`` -- APT/dpkg through the same backend as the Software Center."""

from __future__ import annotations

import typer
from nexus_core import activity, agent_client, runner
from nexus_core import packages as pk
from nexus_core.errors import AbortedError, NexusError

from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.output import confirm, console, print_json, run_agent, table

app = typer.Typer(help="Search, install, remove and upgrade software (APT/dpkg).", no_args_is_help=True)
repo_app = typer.Typer(help="Software repositories.", no_args_is_help=True)
app.add_typer(repo_app, name="repo")


def _show_plan(plan: pk.OperationPlan) -> None:
    console.print(f"[muted]Command:[/muted] {' '.join(plan.command)}")
    if plan.changes:
        table(
            f"{plan.operation}: {len(plan.changes)} change(s)",
            ["Action", "Package", "From", "To"],
            [[c.action, c.name, c.old_version, c.new_version] for c in plan.changes],
        )
    for warning in plan.warnings:
        console.print(f"[warn]! {warning}[/warn]")


def _execute(plan: pk.OperationPlan, yes: bool) -> None:
    if plan.operation != "update" and not plan.changes:
        console.print("[ok]Nothing to do.[/ok]")
        return
    # destructive plans always ask, even with --yes
    if (not yes or plan.destructive) and not confirm("Apply these changes?", default=not plan.destructive):
        raise AbortedError("cancelled; nothing was changed")
    expected = [f"{c.action}:{c.name}" for c in plan.changes]
    if agent_client.available():
        params = {"packages": plan.requested} | ({"expected": expected} if plan.operation != "update" else {})
        result = run_agent(f"apt.{plan.operation}", params)
        if result.get("cancelled"):
            raise AbortedError("cancelled before any package was changed")
    else:
        console.print("[warn]Management agent not installed; falling back to sudo.[/warn]")
        if runner.run_interactive(["sudo", *plan.command]) != 0:
            raise NexusError(f"apt-get {plan.operation} failed")
    activity.record(f"packages.{plan.operation}", " ".join(plan.requested) or plan.operation, "ok")
    console.print(f"[ok]{plan.operation} complete[/ok]")


@app.command("search")
@handle_errors
def search(
    term: str,
    section: str | None = typer.Option(None, help="Limit to an archive section."),
    limit: int = typer.Option(30, help="Maximum results."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Search package names and descriptions."""
    results = pk.search(term, limit=limit, section=section)
    if json_output:
        print_json(results)
        return
    table(
        f"{len(results)} result(s)",
        ["Package", "Installed", "Summary"],
        [[r.name, r.installed_version or "", r.summary] for r in results],
    )


@app.command("show")
@handle_errors
def show(name: str, json_output: bool = typer.Option(False, "--json")) -> None:
    """Package details and dependencies."""
    d = pk.details(name)
    if json_output:
        print_json(d)
        return
    table(
        d.name,
        ["Field", "Value"],
        [
            ["Installed", d.installed_version or "no"],
            ["Candidate", d.candidate_version],
            ["Section", d.section],
            ["Download size", d.download_size_bytes],
            ["Depends", ", ".join(d.depends)],
            ["Recommends", ", ".join(d.recommends)],
            ["Homepage", d.homepage],
        ],
    )
    console.print(d.description, markup=False, highlight=False)


@app.command("list")
@handle_errors
def list_cmd(
    apps_only: bool = typer.Option(False, "--apps", help="Only packages with desktop launchers."),
    upgradable: bool = typer.Option(False, "--upgradable"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Installed packages (or upgradable ones)."""
    if upgradable:
        plan = pk.plan("upgrade")
        if json_output:
            print_json(plan.changes)
        else:
            _show_plan(plan)
        return
    items = pk.installed_applications() if apps_only else pk.installed_packages()
    if json_output:
        print_json(items)
        return
    table(
        f"{len(items)} installed",
        ["Package", "Version", "Summary"],
        [[i.name, i.installed_version, i.summary] for i in items],
    )


@app.command("install")
@handle_errors
def install(
    names: list[str], yes: bool = typer.Option(False, "--yes", "-y"), dry_run: bool = typer.Option(False, "--dry-run")
) -> None:
    """Install packages (shows the exact plan first)."""
    plan = pk.plan("install", names)
    _show_plan(plan)
    if not dry_run:
        _execute(plan, yes)


@app.command("remove")
@handle_errors
def remove(
    names: list[str],
    purge: bool = typer.Option(False, "--purge", help="Also delete system-wide configuration."),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Remove (or purge) packages. Always asks for confirmation."""
    plan = pk.plan("purge" if purge else "remove", names)
    _show_plan(plan)
    if not dry_run:
        _execute(plan, yes=False)


@app.command("update")
@handle_errors
def update(
    upgrade: bool = typer.Option(False, "--upgrade", help="Also upgrade installed packages."),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Refresh package indexes (and optionally upgrade)."""
    _execute(pk.plan("update"), yes)
    if upgrade:
        plan = pk.plan("upgrade")
        _show_plan(plan)
        _execute(plan, yes)


@app.command("history")
@handle_errors
def history(limit: int = 20, json_output: bool = typer.Option(False, "--json")) -> None:
    """Package operation history from /var/log/apt."""
    items = pk.history(limit)
    if json_output:
        print_json(items)
        return
    table(
        "APT history",
        ["Date", "Command", "+", "↑", "−"],
        [[h.start, h.command, len(h.install), len(h.upgrade), len(h.remove) + len(h.purge)] for h in items],
    )


@app.command("lock")
@handle_errors
def lock() -> None:
    """Show whether another program holds the package manager lock."""
    status = pk.lock_status()
    console.print(
        f"locked by {status.holder_name} (pid {status.holder_pid})" if status.locked else "[ok]not locked[/ok]"
    )


@repo_app.command("list")
@handle_errors
def repo_list(json_output: bool = typer.Option(False, "--json")) -> None:
    """Configured APT repositories."""
    repos = pk.repositories()
    if json_output:
        print_json(repos)
        return
    table(
        "Repositories",
        ["URIs", "Suites", "Components", "Signed-By", "Managed"],
        [
            [
                " ".join(r.uris),
                " ".join(r.suites),
                " ".join(r.components),
                r.signed_by,
                "NexusOS" if r.managed_by_nexusos else "system",
            ]
            for r in repos
        ],
    )


@repo_app.command("add")
@handle_errors
def repo_add(
    name: str,
    uri: str,
    suites: list[str] = typer.Option(..., "--suite"),
    components: list[str] = typer.Option([], "--component"),
    signed_by: str = typer.Option(..., "--signed-by"),
) -> None:
    """Add a NexusOS-managed deb822 repository (https, signed)."""
    console.print(pk.validate_repository(name, uri, suites, components, signed_by), markup=False)
    if not confirm("Trust this repository?"):
        raise AbortedError("cancelled")
    run_agent(
        "apt.repo.add", {"name": name, "uri": uri, "suites": suites, "components": components, "signed_by": signed_by}
    )


@repo_app.command("remove")
@handle_errors
def repo_remove(name: str) -> None:
    """Remove a NexusOS-managed repository."""
    if not confirm(f"Remove repository nexusos-{name}?"):
        raise AbortedError("cancelled")
    run_agent("apt.repo.remove", {"name": name})
