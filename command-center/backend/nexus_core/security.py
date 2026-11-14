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
    from nexus_core import privilege

    profile = privilege.access()
    helper = agent_client.available()
    if profile.admin == "none":
        status, detail = (
            "info",
            f"{profile.user} is a standard user: administrative actions are hidden ({profile.reason})",
        )
    elif not helper:
        status, detail = "warn", "admin helper not installed: package, service and gateway changes are unavailable"
    else:
        how = {"not-required": "no password (NOPASSWD)", "required": "password", "unknown": "password if sudo asks"}
        status = "warn" if profile.auth == "not-required" and profile.admin != "root" else "ok"
        detail = f"{profile.user} via sudo · {how[profile.auth]} · audited by nexus-admin"
    checks.append(Check(id="agent", title="Administrative access", status=status, detail=detail))
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
