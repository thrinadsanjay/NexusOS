"""APT preview helpers. Only simulations run here; real changes happen in commands after confirmation."""

from __future__ import annotations

import re
import time
from pathlib import Path

from nexus_cli.core import runner
from nexus_cli.core.errors import DependencyMissingError, NexusError
from nexus_cli.models import UpgradablePackage

APT_LISTS = Path("/var/lib/apt/lists")

# "Inst libfoo [1.0-1] (1.0-2 Ubuntu:26.04/resolute-updates [amd64])"  or new installs without [old].
_INST_RE = re.compile(
    r"^Inst (?P<name>\S+)(?: \[(?P<old>[^\]]+)\])? \((?P<new>\S+)(?: (?P<origin>[^\[\)]+?))?(?: \[[^\]]+\])?\)"
)

UPDATE_COMMAND = ["sudo", "apt-get", "update"]
UPGRADE_COMMAND = ["sudo", "apt-get", "upgrade"]


def require_apt() -> None:
    if runner.which("apt-get") is None:
        raise DependencyMissingError("apt-get not found", hint="`nexus system update` supports APT-based systems only")


def parse_simulation(output: str) -> list[UpgradablePackage]:
    packages: list[UpgradablePackage] = []
    for line in output.splitlines():
        match = _INST_RE.match(line.strip())
        if match:
            packages.append(
                UpgradablePackage(
                    name=match["name"],
                    current_version=match["old"],
                    candidate_version=match["new"],
                    # Simulation lists every suite carrying the version; the first is enough.
                    origin=(match["origin"] or "").split(",")[0].strip() or None,
                )
            )
    return packages


def simulate_upgrade() -> list[UpgradablePackage]:
    """Run ``apt-get --simulate upgrade`` (no root required, changes nothing)."""
    require_apt()
    result = runner.run(["apt-get", "--simulate", "-o", "Debug::NoLocking=1", "upgrade"], timeout=120)
    if not result.ok:
        raise NexusError("APT simulation failed", hint=runner.first_line(result.stderr) or None)
    return parse_simulation(result.stdout)


def apt_lists_age_hours(lists_dir: Path = APT_LISTS) -> float | None:
    """Age of the newest package index, or None if unknown."""
    try:
        newest = max((p.stat().st_mtime for p in lists_dir.iterdir() if p.is_file()), default=None)
    except OSError:
        return None
    if newest is None:
        return None
    return (time.time() - newest) / 3600.0


def simulate_autoremove_count() -> int | None:
    if runner.which("apt-get") is None:
        return None
    result = runner.run(["apt-get", "--simulate", "-o", "Debug::NoLocking=1", "autoremove"], timeout=60)
    if not result.ok:
        return None
    return sum(1 for line in result.stdout.splitlines() if line.startswith("Remv "))
