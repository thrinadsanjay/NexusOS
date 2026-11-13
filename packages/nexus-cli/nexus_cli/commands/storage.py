"""``nexus storage`` -- disks, usage and SMART health (read-only from the CLI)."""

from __future__ import annotations

import typer
from nexus_core import storage as st

from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.output import print_json, table

app = typer.Typer(help="Disks, filesystems and health.", no_args_is_help=True)


@app.command("list")
@handle_errors
def list_cmd(json_output: bool = typer.Option(False, "--json")) -> None:
    """Disks and partitions."""
    devs = st.devices()
    if json_output:
        print_json(devs)
        return
    rows = []
    for d in devs:
        rows.append([d.path, d.media, d.size, d.model, d.serial, ""])
        rows += [[f"  {c.path}", c.type, c.size, c.fstype, c.label, ", ".join(c.mountpoints)] for c in d.children]
    table("Block devices", ["Device", "Type", "Bytes", "Model/FS", "Serial/Label", "Mounted"], rows)


@app.command("usage")
@handle_errors
def usage(json_output: bool = typer.Option(False, "--json")) -> None:
    """Filesystem usage."""
    items = st.usage()
    if json_output:
        print_json(items)
        return
    table(
        "Usage",
        ["Mount", "Source", "Type", "Used", "Size", "%"],
        [[u.mount, u.source, u.fstype, u.used, u.size, round(100 * u.used / u.size) if u.size else 0] for u in items],
    )
    table(
        "Swap",
        ["Device", "Type", "Size KiB", "Used KiB"],
        [[s.device, s.type, s.size_kib, s.used_kib] for s in st.swaps()],
    )


@app.command("health")
@handle_errors
def health(device: str | None = typer.Argument(None, help="e.g. /dev/nvme0n1 (default: all disks)")) -> None:
    """SMART health (through the management agent)."""
    targets = [device] if device else [d.path for d in st.devices() if d.type == "disk"]
    results = [st.smart(t) for t in targets]
    table(
        "SMART",
        ["Device", "Available", "Passed", "Temp °C", "Power-on h", "Wear %", "Note"],
        [
            [r.device, r.available, r.passed, r.temperature_c, r.power_on_hours, r.percentage_used, r.message]
            for r in results
        ],
    )
