"""Input validation shared by every frontend and the privileged agent.

Everything that ends up in a command line, a configuration file or a network
request is validated here first. Validators raise :class:`ValidationError`.
"""

from __future__ import annotations

import ipaddress
import re
import socket

from nexus_core.errors import ValidationError

DEB_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]{1,127}(:(amd64|i386|all))?$")
HOST_LABEL_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
SSH_USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$")
UNIT_RE = re.compile(r"^[A-Za-z0-9@_.:\-]{1,200}\.(service|socket|timer|target|mount|path)$")
URL_PATH_RE = re.compile(r"^/[A-Za-z0-9._~/\-]*$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,63}$")
DOCKER_REF_RE = re.compile(r"^[a-z0-9]+([._\-/:@][A-Za-z0-9]+)*$")
DOCKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}$")
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

# Networks a gateway backend may never point at, even with "allow public" (SSRF guard).
FORBIDDEN_BACKEND_NETS = [
    ipaddress.ip_network(n)
    for n in ("169.254.0.0/16", "fe80::/10", "0.0.0.0/8", "224.0.0.0/4", "ff00::/8", "100.100.100.200/32")
]


def package_name(name: str) -> str:
    if not isinstance(name, str) or not DEB_PACKAGE_RE.match(name):
        raise ValidationError(f"invalid package name: {name!r}")
    return name


def package_names(names: list[str]) -> list[str]:
    if not names:
        raise ValidationError("no packages given")
    if len(names) > 200:
        raise ValidationError("too many packages in one operation (max 200)")
    return [package_name(n) for n in names]


def hostname(value: str, *, allow_wildcard: bool = False) -> str:
    value = (value or "").strip().rstrip(".").lower()
    if not value or len(value) > 253:
        raise ValidationError(f"invalid hostname: {value!r}")
    labels = value.split(".")
    if allow_wildcard and labels[0] == "*":
        labels = labels[1:]
    if not labels or not all(HOST_LABEL_RE.match(label) for label in labels):
        raise ValidationError(f"invalid hostname: {value!r}")
    return value


def host_or_ip(value: str) -> str:
    value = (value or "").strip()
    try:
        return str(ipaddress.ip_address(value.strip("[]")))
    except ValueError:
        return hostname(value)


def port(value: int | str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"invalid port: {value!r}") from None
    if not 1 <= number <= 65535:
        raise ValidationError(f"port out of range: {number}")
    return number


def ssh_user(value: str) -> str:
    if not SSH_USER_RE.match(value or ""):
        raise ValidationError(f"invalid SSH username: {value!r}")
    return value


def unit_name(value: str) -> str:
    if not UNIT_RE.match(value or ""):
        raise ValidationError(f"invalid systemd unit name: {value!r}")
    return value


def display_name(value: str) -> str:
    value = (value or "").strip()
    if not NAME_RE.match(value):
        raise ValidationError(f"invalid name: {value!r} (letters, digits, space, '_', '.', '-'; max 64)")
    return value


def single_line(value: str, *, max_len: int = 512, field: str = "value") -> str:
    if value is None:
        return ""
    if CONTROL_CHARS.search(value) or len(value) > max_len:
        raise ValidationError(f"{field} contains control characters or is too long")
    return value


def url_path(value: str) -> str:
    if not URL_PATH_RE.match(value or "") or ".." in value:
        raise ValidationError(f"invalid URL path: {value!r}")
    return value


def docker_ref(value: str) -> str:
    if not value or len(value) > 255 or not DOCKER_REF_RE.match(value):
        raise ValidationError(f"invalid image reference: {value!r}")
    return value


def docker_id(value: str) -> str:
    if not DOCKER_ID_RE.match(value or ""):
        raise ValidationError(f"invalid container/volume/network name: {value!r}")
    return value


def resolve_addresses(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return [ipaddress.ip_address(host.strip("[]"))]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValidationError(f"cannot resolve {host!r}") from exc
    return sorted({ipaddress.ip_address(info[4][0]) for info in infos}, key=str)


def is_private_address(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return addr.is_loopback or (addr.is_private and not addr.is_link_local)


def backend_destination(host: str, *, allow_public: bool = False) -> list[str]:
    """Validate a gateway backend host against SSRF rules; returns resolved addresses.

    * link-local / cloud metadata / multicast / unspecified addresses are always refused
    * public addresses are refused unless ``allow_public`` is explicitly set
    """
    host = host_or_ip(host)
    addresses = resolve_addresses(host)
    for addr in addresses:
        if any(addr in net for net in FORBIDDEN_BACKEND_NETS) or addr.is_unspecified or addr.is_multicast:
            raise ValidationError(f"backend {host} resolves to forbidden address {addr}")
        if not allow_public and not is_private_address(addr):
            raise ValidationError(
                f"backend {host} resolves to public address {addr}; enable 'allow public backend' explicitly"
            )
    return [str(a) for a in addresses]
