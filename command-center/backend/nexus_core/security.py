"""Security overview: privilege boundaries and exposure, read-only."""

from __future__ import annotations

import grp

from pydantic import BaseModel

from nexus_core import agent_client, runner


class Check(BaseModel):
    id: str
    title: str
    status: str  # ok | warn | info | unknown
    detail: str


def _group_members(name: str) -> list[str]:
    try:
        return list(grp.getgrnam(name).gr_mem)
    except KeyError:
        return []


def listening_ports() -> list[dict]:
    """TCP/UDP listeners (no process names: that would need root)."""
    result = runner.run(["ss", "-H", "-tuln"], timeout=10)
    out = []
    for line in result.stdout.splitlines():
        p = line.split()
        if len(p) >= 5:
            local = p[4]
            addr, _, port = local.rpartition(":")
            out.append(
                {
                    "proto": p[0],
                    "address": addr.strip("[]"),
                    "port": port,
                    "exposed": addr.strip("[]") not in ("127.0.0.1", "::1", "127.0.0.53%lo", "127.0.0.54"),
                }
            )
    return out


def secret_service_available() -> bool:
    try:
        import secretstorage

        conn = secretstorage.dbus_init()
        return secretstorage.check_service_availability(conn)
    except Exception:
        return False


def overview() -> list[Check]:
    checks = []
    agent = agent_client.available()
    checks.append(
        Check(
            id="agent",
            title="Management agent",
            status="ok" if agent else "warn",
            detail="socket-activated, polkit-authorized"
            if agent
            else "not installed: package and gateway operations are unavailable",
        )
    )
    checks.append(
        Check(
            id="polkit",
            title="polkit",
            status="ok" if runner.which("pkcheck") else "warn",
            detail="pkcheck present" if runner.which("pkcheck") else "pkcheck missing: agent denies all",
        )
    )
    docker_users = _group_members("docker")
    checks.append(
        Check(
            id="docker-group",
            title="Docker group",
            status="warn" if docker_users else "ok",
            detail=("root-equivalent access for: " + ", ".join(docker_users))
            if docker_users
            else "no users in the docker group",
        )
    )
    ss = secret_service_available()
    checks.append(
        Check(
            id="secrets",
            title="Secret Service (KDE Wallet)",
            status="ok" if ss else "warn",
            detail="available for SSH credentials" if ss else "unavailable: saving passwords is disabled",
        )
    )
    exposed = [p for p in listening_ports() if p["exposed"]]
    checks.append(
        Check(
            id="exposure",
            title="Network listeners",
            status="info" if exposed else "ok",
            detail=f"{len(exposed)} port(s) listening on non-loopback addresses"
            if exposed
            else "no services listening beyond loopback",
        )
    )
    return checks
