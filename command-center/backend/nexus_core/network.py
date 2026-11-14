"""Networking through NetworkManager (nmcli) and iproute2. No other network engine.

Changes that could disconnect the machine use NetworkManager checkpoints: a checkpoint
is created with a rollback timeout before the change; if the user does not confirm
connectivity in time, NetworkManager restores the previous configuration by itself.
"""

from __future__ import annotations

import ipaddress
import json
import re

from pydantic import BaseModel, Field

from nexus_core import agent_client, runner, validation
from nexus_core.errors import DependencyMissingError, NexusError, ValidationError


def _nmcli(*args: str, timeout: float = 20) -> runner.CommandResult:
    if runner.which("nmcli") is None:
        raise DependencyMissingError("NetworkManager (nmcli) is not installed", hint="sudo apt install network-manager")
    return runner.run(["nmcli", "-t", "-e", "yes", *args], timeout=timeout)


def _split(line: str) -> list[str]:
    """Split nmcli terse output (':' separated, '\\:' escaped)."""
    return [p.replace("\\:", ":").replace("\\\\", "\\") for p in re.split(r"(?<!\\):", line)]


class Device(BaseModel):
    name: str
    type: str
    state: str
    connection: str
    addresses: list[str] = Field(default_factory=list)
    mac: str | None = None


class Connection(BaseModel):
    name: str
    uuid: str
    type: str
    device: str
    active: bool


class WifiNetwork(BaseModel):
    ssid: str
    signal: int
    security: str
    in_use: bool


def devices() -> list[Device]:
    result = _nmcli("-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status")
    out = []
    for line in result.stdout.splitlines():
        p = _split(line)
        if len(p) >= 4 and p[1] not in ("loopback",):
            out.append(Device(name=p[0], type=p[1], state=p[2], connection=p[3]))
    addrs = interfaces()
    for d in out:
        info = addrs.get(d.name, {})
        d.addresses, d.mac = info.get("addresses", []), info.get("mac")
    return out


def interfaces() -> dict[str, dict]:
    result = runner.run(["ip", "-j", "addr"], timeout=10)
    out = {}
    for item in json.loads(result.stdout or "[]") if result.ok else []:
        out[item["ifname"]] = {
            "mac": item.get("address"),
            "state": item.get("operstate"),
            "mtu": item.get("mtu"),
            "addresses": [f"{a['local']}/{a['prefixlen']}" for a in item.get("addr_info", [])],
        }
    return out


def routes() -> list[dict]:
    out = []
    for family in ("-4", "-6"):
        result = runner.run(["ip", "-j", family, "route"], timeout=10)
        out += json.loads(result.stdout or "[]") if result.ok else []
    return out


def connections() -> list[Connection]:
    result = _nmcli("-f", "NAME,UUID,TYPE,DEVICE,ACTIVE", "connection", "show")
    out = []
    for line in result.stdout.splitlines():
        p = _split(line)
        if len(p) >= 5:
            out.append(Connection(name=p[0], uuid=p[1], type=p[2], device=p[3], active=p[4] == "yes"))
    return out


def wifi_networks(rescan: bool = False) -> list[WifiNetwork]:
    result = _nmcli(
        "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes" if rescan else "no"
    )
    out = []
    for line in result.stdout.splitlines():
        p = _split(line)
        if len(p) >= 4 and p[1]:
            out.append(WifiNetwork(in_use=p[0] == "*", ssid=p[1], signal=int(p[2] or 0), security=p[3] or "open"))
    return out


def dns() -> dict:
    result = runner.run(["resolvectl", "dns"], timeout=10)
    servers: dict[str, list[str]] = {}
    for line in result.stdout.splitlines() if result.ok else []:
        name, _, rest = line.partition(":")
        if rest.strip():
            servers[name.strip()] = rest.split()
    if not servers:
        try:
            lines = open("/etc/resolv.conf", encoding="utf-8").read().splitlines()  # noqa: SIM115
            servers["resolv.conf"] = [ln.split()[1] for ln in lines if ln.startswith("nameserver ")]
        except OSError:
            pass
    return servers


def connectivity() -> str:
    result = _nmcli("networking", "connectivity", "check", timeout=30)
    return result.stdout.strip() or "unknown"


def connection_action(name_or_uuid: str, action: str) -> None:
    if action not in ("up", "down"):
        raise ValidationError("action must be up or down")
    validation.single_line(name_or_uuid, max_len=128, field="connection")
    result = _nmcli("connection", action, "id", name_or_uuid, timeout=90)
    if not result.ok:
        raise NexusError(f"could not bring connection {action}", hint=runner.first_line(result.stderr))


class StaticIPv4(BaseModel):
    connection: str
    address: str  # CIDR
    gateway: str | None = None
    dns: list[str] = Field(default_factory=list)


def static_ipv4_argv(cfg: StaticIPv4) -> list[str]:
    iface = ipaddress.ip_interface(cfg.address)
    if iface.version != 4:
        raise ValidationError("address must be IPv4 CIDR, e.g. 192.168.1.20/24")
    if cfg.gateway and ipaddress.ip_address(cfg.gateway) not in iface.network:
        raise ValidationError("gateway must be inside the address's network")
    for server in cfg.dns:
        ipaddress.ip_address(server)
    argv = [
        "nmcli",
        "connection",
        "modify",
        "id",
        validation.single_line(cfg.connection, max_len=128),
        "ipv4.method",
        "manual",
        "ipv4.addresses",
        str(iface),
    ]
    argv += ["ipv4.gateway", cfg.gateway or ""]
    argv += ["ipv4.dns", ",".join(cfg.dns)]
    return argv


CHECKPOINT_TIMEOUT = 60


def apply_with_checkpoint(argv: list[str], connection: str, rollback_seconds: int = CHECKPOINT_TIMEOUT) -> str:
    """Create an NM checkpoint (auto-rollback after *rollback_seconds*), apply, re-activate.

    Returns the checkpoint object path; call :func:`confirm_checkpoint` once connectivity
    is verified, otherwise NetworkManager rolls back automatically.
    """
    cp = runner.run(
        [
            "gdbus",
            "call",
            "--system",
            "--dest",
            "org.freedesktop.NetworkManager",
            "--object-path",
            "/org/freedesktop/NetworkManager",
            "--method",
            "org.freedesktop.NetworkManager.CheckpointCreate",
            "[]",
            str(rollback_seconds),
            "1",
        ],
        timeout=120,
    )
    match = re.search(r"objectpath '([^']+)'", cp.stdout)
    if not cp.ok or not match:
        raise NexusError(
            "could not create a NetworkManager checkpoint; change not applied", hint=runner.first_line(cp.stderr)
        )
    result = runner.run(argv, timeout=60)
    if not result.ok:
        raise NexusError("network change failed (checkpoint will roll back)", hint=runner.first_line(result.stderr))
    connection_action(connection, "up")
    return match.group(1)


def confirm_checkpoint(path: str) -> None:
    if not re.fullmatch(r"/org/freedesktop/NetworkManager/Checkpoint/\d+", path):
        raise ValidationError("invalid checkpoint path")
    runner.run(
        [
            "gdbus",
            "call",
            "--system",
            "--dest",
            "org.freedesktop.NetworkManager",
            "--object-path",
            "/org/freedesktop/NetworkManager",
            "--method",
            "org.freedesktop.NetworkManager.CheckpointDestroy",
            path,
        ],
        timeout=60,
    )


class DiagnosticResult(BaseModel):
    tool: str
    target: str
    ok: bool
    output: str


def diagnose(target: str) -> list[DiagnosticResult]:
    target = validation.host_or_ip(target)
    checks = [
        ("dns", ["getent", "ahosts", target]),
        ("ping", ["ping", "-c", "3", "-W", "2", target]),
        ("route", ["ip", "route", "get", target]),
        ("trace", ["tracepath", "-n", "-m", "15", target]),
    ]
    out = []
    for name, argv in checks:
        if name == "route":
            try:
                ipaddress.ip_address(target)
            except ValueError:
                continue
        result = runner.run(argv, timeout=40)
        out.append(
            DiagnosticResult(
                tool=name, target=target, ok=result.ok, output=(result.stdout or result.stderr).strip()[-4000:]
            )
        )
    return out


def firewall_status(prompt: bool = False) -> dict:
    """ufw status (root only). Without ``prompt`` a password-protected sudo reports ``locked``."""
    from nexus_core import privilege

    try:
        return agent_client.call("firewall.status", label="Read firewall status", prompt=prompt)
    except DependencyMissingError as exc:
        return {"installed": runner.which("ufw") is not None, "output": exc.message}
    except privilege.AuthRequiredError:
        return {"installed": runner.which("ufw") is not None, "locked": True, "output": ""}
    except (privilege.AccessDeniedError, privilege.AuthCancelledError) as exc:
        return {"installed": runner.which("ufw") is not None, "denied": True, "output": exc.message}


def proxy_settings() -> dict:
    """KDE proxy configuration (read-only; edited in the KDE proxy settings module)."""
    from pathlib import Path

    cfg = Path.home() / ".config" / "kioslaverc"
    out: dict[str, str] = {}
    if cfg.exists():
        section = ""
        for line in cfg.read_text().splitlines():
            if line.startswith("["):
                section = line
            elif section == "[Proxy Settings]" and "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
    return out
