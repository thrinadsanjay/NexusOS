"""Parse os-release(5) and NexusOS release metadata."""

from __future__ import annotations

import shlex
from pathlib import Path

from nexus_cli.models import OSRelease

OS_RELEASE_PATHS = (Path("/etc/os-release"), Path("/usr/lib/os-release"))
NEXUSOS_RELEASE_PATH = Path("/usr/lib/nexusos/release")


def parse_key_value_file(text: str) -> dict[str, str]:
    """Parse a shell-compatible KEY=VALUE file without executing it."""
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key.replace("_", "").isalnum():
            continue
        try:
            parts = shlex.split(value, comments=False, posix=True)
        except ValueError:
            continue
        result[key] = parts[0] if parts else ""
    return result


def read_os_release(paths: tuple[Path, ...] = OS_RELEASE_PATHS) -> OSRelease:
    for path in paths:
        try:
            data = parse_key_value_file(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        return OSRelease(
            name=data.get("NAME", "Linux"),
            pretty_name=data.get("PRETTY_NAME", data.get("NAME", "Linux")),
            id=data.get("ID", "linux"),
            id_like=data.get("ID_LIKE"),
            version_id=data.get("VERSION_ID"),
            version=data.get("VERSION"),
            codename=data.get("VERSION_CODENAME") or data.get("UBUNTU_CODENAME"),
            build_id=data.get("BUILD_ID"),
            variant=data.get("VARIANT"),
        )
    return OSRelease()


def read_nexusos_release(path: Path = NEXUSOS_RELEASE_PATH) -> dict[str, str]:
    try:
        return parse_key_value_file(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
