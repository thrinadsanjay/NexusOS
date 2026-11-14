"""systemd service inspection and control.

Read operations run unprivileged as the logged-in user. Start/stop/restart/
enable/disable are administrative: they run through the user's sudo rights
(``nexus-admin`` operation ``service.control``, see nexus_core.privilege).
Only units on the approved list can be controlled from NexusOS frontends.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from nexus_core import runner, validation
from nexus_core.errors import NexusError, ValidationError
from nexus_core.redact import redact_text

# Units NexusOS frontends may control. Others are shown read-only.
APPROVED_UNITS = {
    "docker.service",
    "containerd.service",
    "nginx.service",
    "ollama.service",
    "libvirtd.service",
    "virtqemud.socket",
    "ssh.service",
    "cups.service",
    "bluetooth.service",
    "NetworkManager.service",
    "ufw.service",
    "smartmontools.service",
    "nexusos-agent.socket",
    "fwupd.service",
    "power-profiles-daemon.service",
    "avahi-daemon.service",
    "certbot.timer",
}
Action = Literal["start", "stop", "restart", "enable", "disable"]


class Unit(BaseModel):
    name: str
    load: str
    active: str
    sub: str
    description: str
    approved: bool = False


def list_units(kind: str = "service") -> list[Unit]:
    result = runner.run(
        ["systemctl", "list-units", f"--type={kind}", "--all", "--no-pager", "--output=json"], timeout=15
    )
    if not result.ok:
        raise NexusError("cannot query systemd", hint=runner.first_line(result.stderr) or "is systemd running?")
    units = []
    for item in json.loads(result.stdout or "[]"):
        name = item.get("unit", "")
        units.append(
            Unit(
                name=name,
                load=item.get("load", ""),
                active=item.get("active", ""),
                sub=item.get("sub", ""),
                description=item.get("description", ""),
                approved=name in APPROVED_UNITS,
            )
        )
    return units


def is_active(unit: str) -> str:
    """Return systemd's ActiveState (``active``, ``inactive``, ``failed``…) or ``not-found``/``unknown``."""
    validation.unit_name(unit)
    result = runner.run(["systemctl", "show", unit, "--property=ActiveState,LoadState"], timeout=5)
    if not result.found:
        return "unknown"
    # Parse key=value: systemctl prints properties in its own order, not the order requested.
    props = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if props.get("LoadState") == "not-found":
        return "not-found"
    return props.get("ActiveState") or "unknown"


def control(unit: str, action: Action) -> dict:
    validation.unit_name(unit)
    if unit not in APPROVED_UNITS:
        raise ValidationError(f"{unit} is not on the list of services NexusOS may control")
    if action not in ("start", "stop", "restart", "enable", "disable"):
        raise ValidationError(f"unsupported action {action!r}")
    from nexus_core import agent_client

    return agent_client.call("service.control", {"unit": unit, "action": action}, label=f"{action.title()} {unit}")


def logs(unit: str, lines: int = 200) -> str:
    """Recent journal lines for a unit (secrets redacted). Needs membership of adm/systemd-journal for system units."""
    validation.unit_name(unit)
    lines = max(1, min(int(lines), 2000))
    result = runner.run(["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "short-iso"], timeout=20)
    if not result.found:
        raise NexusError("journalctl not available")
    text = result.stdout or result.stderr
    if not text.strip() or "No journal files were found" in text or "-- No entries --" in text:
        from nexus_core import privilege

        if not privilege.access().journal:
            return (
                f"No log lines visible to {privilege.access().user}.\n"
                "System service logs are readable by members of the 'adm' or 'systemd-journal' group."
            )
    return redact_text(text)
