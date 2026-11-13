"""Known-host verification (trust on first use, with fingerprints shown to the user)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from nexus_core import runner, validation
from nexus_core.errors import DependencyMissingError, NexusError


class HostKey(BaseModel):
    key_type: str
    fingerprint: str
    line: str


def _target(host: str, port: int) -> str:
    return host if port == 22 else f"[{host}]:{port}"


def known_hosts_file() -> Path:
    return Path.home() / ".ssh" / "known_hosts"


def is_known(host: str, port: int = 22, known_hosts: Path | None = None) -> bool:
    host = validation.host_or_ip(host)
    result = runner.run(
        ["ssh-keygen", "-F", _target(host, validation.port(port)), "-f", str(known_hosts or known_hosts_file())],
        timeout=10,
    )
    return result.ok and bool(result.stdout.strip())


def scan(host: str, port: int = 22) -> list[HostKey]:
    """Fetch the server's host keys and their SHA256 fingerprints (to show before trusting)."""
    host = validation.host_or_ip(host)
    port = validation.port(port)
    if runner.which("ssh-keyscan") is None:
        raise DependencyMissingError("ssh-keyscan not found", hint="sudo apt install openssh-client")
    scan_result = runner.run(["ssh-keyscan", "-T", "5", "-p", str(port), host], timeout=15)
    lines = [ln for ln in scan_result.stdout.splitlines() if ln and not ln.startswith("#")]
    if not lines:
        raise NexusError(f"could not fetch host keys from {host}:{port}", hint="check host, port and firewall")
    keys = []
    for line in lines:
        fp = _fingerprint(line)
        keys.append(HostKey(key_type=line.split()[1], fingerprint=fp, line=line))
    return keys


def _fingerprint(line: str) -> str:
    import subprocess

    proc = subprocess.run(
        ["ssh-keygen", "-lf", "-"],
        input=line,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    parts = proc.stdout.split()
    return parts[1] if len(parts) > 1 else "unknown"


def trust(keys: list[HostKey], known_hosts: Path | None = None) -> None:
    """Append confirmed keys to ~/.ssh/known_hosts (called only after the user compared fingerprints)."""
    target = known_hosts or known_hosts_file()
    target.parent.mkdir(mode=0o700, exist_ok=True)
    existing = target.read_text() if target.exists() else ""
    with target.open("a") as handle:
        for key in keys:
            if key.line not in existing:
                handle.write(key.line.rstrip("\n") + "\n")
    target.chmod(0o600)
