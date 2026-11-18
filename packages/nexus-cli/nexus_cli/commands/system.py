"""``nexus system`` -- information, health checks, updates and cleanup."""

from __future__ import annotations

from pathlib import Path

import typer
from nexus_core import cleanup as cleanup_service
from nexus_core import health as health_service
from nexus_core import packages, runner
from nexus_core.errors import AbortedError, NexusError
from nexus_core.system import collect_system_info, human_bytes, human_duration
from rich.table import Table

from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.output import confirm, console, print_json, status_text, table

app = typer.Typer(help="System information, health checks, updates and cleanup.", no_args_is_help=True)

STALE_LISTS_HOURS = 24.0


@app.command("info")
@handle_errors
def info(json_output: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Show hardware, OS and session information (read-only)."""
    data = collect_system_info()
    if json_output:
        print_json(data)
        return
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="accent", no_wrap=True)
    table.add_column()
    table.add_row("Hostname", data.hostname)
    table.add_row(
        "OS", data.os.pretty_name + (f"  [muted](build {data.os.build_id})[/muted]" if data.os.build_id else "")
    )
    table.add_row("Kernel", data.kernel)
    table.add_row("Architecture", data.architecture)
    table.add_row("CPU", f"{data.cpu_model} ({data.cpu_count} threads)")
    if data.memory:
        table.add_row(
            "Memory",
            f"{human_bytes(data.memory.total_bytes - data.memory.available_bytes)} / "
            f"{human_bytes(data.memory.total_bytes)} ({data.memory.used_percent:.0f}%)",
        )
    for disk in data.disks:
        table.add_row(
            f"Disk {disk.mount}",
            f"{human_bytes(disk.total_bytes - disk.free_bytes)} / {human_bytes(disk.total_bytes)} "
            f"({disk.used_percent:.0f}%)",
        )
    table.add_row("Uptime", human_duration(data.uptime_seconds))
    if data.load_average:
        table.add_row("Load", " ".join(f"{v:.2f}" for v in data.load_average))
    table.add_row("Desktop", " / ".join(filter(None, [data.desktop_session, data.session_type])) or "n/a")
    table.add_row("Virtualisation", data.virtualization or "n/a")
    console.print(table)


@app.command("health")
@handle_errors
def health(json_output: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Run safe, read-only health checks. Exits 1 if any check fails."""
    report = health_service.run_health_checks()
    if json_output:
        print_json(report)
    else:
        table = Table(title="NexusOS health", title_style="accent", header_style="muted")
        table.add_column("Check", style="bold")
        table.add_column("Status", no_wrap=True)
        table.add_column("Detail")
        for check in report.checks:
            detail = check.detail + (f"\n[muted]{check.hint}[/muted]" if check.hint else "")
            table.add_row(check.name, status_text(check.status), detail)
        console.print(table)
    if report.failed:
        raise typer.Exit(1)


@app.command("update")
@handle_errors
def update(
    refresh: bool = typer.Option(False, "--refresh", help="Refresh package indexes first (sudo apt-get update)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only show the preview."),
) -> None:
    """Preview available APT upgrades, then upgrade after explicit confirmation."""
    packages.require_apt()
    if refresh:
        console.print(f"[muted]Will run:[/muted] {' '.join(packages.UPDATE_COMMAND)}")
        if dry_run:
            console.print("[muted]--dry-run: skipping index refresh.[/muted]")
        elif confirm("Refresh package indexes now?"):
            if runner.run_interactive(packages.UPDATE_COMMAND) != 0:
                raise NexusError("apt-get update failed")
        else:
            raise AbortedError("cancelled")

    age = packages.apt_lists_age_hours()
    if age is not None and age > STALE_LISTS_HOURS and not refresh:
        console.print(f"[warn]Package indexes are {age:.0f}h old; use --refresh for an up-to-date preview.[/warn]")

    upgrades = packages.simulate_upgrade()
    if not upgrades:
        console.print("[ok]System is up to date[/ok] (according to the current package indexes).")
        return

    table = Table(title=f"{len(upgrades)} package(s) to upgrade", title_style="accent", header_style="muted")
    table.add_column("Package")
    table.add_column("Installed", style="muted")
    table.add_column("Candidate", style="accent")
    table.add_column("Origin", style="muted")
    for pkg in upgrades:
        table.add_row(pkg.name, pkg.current_version or "(new)", pkg.candidate_version, pkg.origin or "")
    console.print(table)

    if dry_run:
        return
    console.print(f"[muted]Will run:[/muted] {' '.join(packages.UPGRADE_COMMAND)}  [muted](requires sudo)[/muted]")
    if not confirm("Proceed with the upgrade?"):
        raise AbortedError("cancelled; nothing was changed")
    code = runner.run_interactive(packages.UPGRADE_COMMAND)
    if code != 0:
        raise NexusError(f"apt-get upgrade exited with status {code}")


@app.command("cleanup")
@handle_errors
def cleanup(
    apply: bool = typer.Option(False, "--apply", help="Perform the cleanup (asks before each step)."),
    json_output: bool = typer.Option(False, "--json", help="Emit the plan as JSON."),
) -> None:
    """Preview reclaimable disk space; with --apply, clean after per-item confirmation."""
    plan = cleanup_service.plan_cleanup()
    if json_output:
        print_json(plan)
        return
    if not plan:
        console.print("[ok]Nothing to clean.[/ok]")
        return
    table = Table(title="Cleanup preview", title_style="accent", header_style="muted")
    table.add_column("Item")
    table.add_column("Reclaimable", justify="right")
    table.add_column("Needs sudo", justify="center")
    table.add_column("Action", style="muted")
    for item in plan:
        action = " ".join(item.command) if item.command else f"empty {', '.join(item.paths)}"
        size = human_bytes(item.reclaimable_bytes) if item.reclaimable_bytes is not None else "?"
        table.add_row(item.description, size, "yes" if item.privileged else "no", action)
    console.print(table)
    if not apply:
        console.print("[muted]Preview only. Re-run with --apply to clean.[/muted]")
        return

    for item in plan:
        if item.reclaimable_bytes == 0:
            continue
        if not confirm(f"Clean: {item.description}?"):
            continue
        if item.command:
            code = runner.run_interactive(item.command)
            console.print(status_text("ok" if code == 0 else "fail") + f" {item.id}")
        else:
            freed = sum(cleanup_service.clean_user_path(Path(p)) for p in item.paths)
            console.print(status_text("ok") + f" {item.id}: freed {human_bytes(freed)}")


@app.command("desktop-status")
@handle_errors
def desktop_status(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON (used by the desktop status panel)."),
    no_updates: bool = typer.Option(False, "--no-updates", help="Skip the (cached) APT update check."),
) -> None:
    """Health, alerts, storage and services shown by the desktop System Status panel."""
    from nexus_core import desktop_status as ds

    report = ds.collect(include_updates=not no_updates)
    if json_output:
        print_json(report)
        return
    console.print(f"Services   {report.services.running} running, {report.services.failed} failed")
    if report.updates.known:
        console.print(f"Updates    {report.updates.security} security, {report.updates.regular} regular")
    if report.root:
        console.print(f"Storage    {report.root.mount} {report.root.percent:.0f} % used")
    for alert in report.alerts:
        level = "fail" if alert.severity == "critical" else "warn"
        console.print(status_text(level) + f" {alert.title}  {alert.detail}")


# ----------------------------------------------------------------------------- v0.2
@app.command("services")
@handle_errors
def services_cmd(
    action: str = typer.Argument("list", help="list | status | start | stop | restart | enable | disable | logs"),
    unit: str | None = typer.Argument(None, help="systemd unit, e.g. nginx.service"),
    all_units: bool = typer.Option(False, "--all", help="List every service, not only NexusOS-manageable ones."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Inspect and control approved systemd services (changes are authorized by polkit)."""
    from nexus_core import activity
    from nexus_core import services as svc

    if action == "list":
        units = [u for u in svc.list_units() if all_units or u.approved]
        if json_output:
            print_json(units)
            return
        table(
            "Services" + ("" if all_units else " (manageable by NexusOS)"),
            ["Unit", "Active", "Sub", "Description"],
            [[u.name, u.active, u.sub, u.description] for u in units],
        )
        return
    if not unit:
        raise NexusError("a unit name is required", hint="e.g. nexus system services restart nginx.service")
    if action == "status":
        console.print(f"{unit}: {svc.is_active(unit)}")
    elif action == "logs":
        console.print(svc.logs(unit), markup=False, highlight=False)
    elif action in ("start", "stop", "restart", "enable", "disable"):
        console.print(
            f"[muted]Will run:[/muted] systemctl {action} {unit}  [muted](polkit asks for authorization)[/muted]"
        )
        if action in ("stop", "disable") and not confirm(f"{action} {unit}?"):
            raise AbortedError("cancelled")
        svc.control(unit, action)  # type: ignore[arg-type]
        activity.record(f"service.{action}", unit, "ok")
        console.print(f"[ok]{unit}: {action} done[/ok]")
    else:
        raise NexusError(f"unknown action {action!r}")


@app.command("settings")
@handle_errors
def settings_cmd(
    key: str | None = typer.Argument(None, help="hostname | timezone | ntp | open"),
    value: str | None = typer.Argument(None, help="new value (hostname, time zone, on/off, or a KCM name)"),
) -> None:
    """Show system settings, change hostname/time zone/NTP, or open a KDE settings module."""
    from nexus_core import settings as st

    if key is None:
        t = st.time_status()
        table(
            "System settings",
            ["Setting", "Value"],
            [
                ["Hostname", st.hostname()],
                ["Time zone", t.timezone],
                ["NTP enabled", t.ntp_enabled],
                ["Clock synchronised", t.ntp_synchronized],
                ["Locale", st.locale_status().get("System Locale", "")],
            ],
        )
        table(
            "Desktop settings (open with: nexus system settings open <module>)",
            ["Category", "Setting", "Module"],
            [[e.category, e.title, e.kcm or f"native:{e.native}"] for e in st.CATALOG],
        )
        return
    if value is None:
        raise NexusError("a value is required")
    if key == "hostname":
        st.set_hostname(value)
    elif key == "timezone":
        st.set_timezone(value)
    elif key == "ntp":
        st.set_ntp(value.lower() in ("on", "true", "yes", "1"))
    elif key == "open":
        st.open_kcm(value)
    else:
        raise NexusError(f"unknown setting {key!r}")
    console.print("[ok]done[/ok]")
