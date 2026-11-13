"""Certificate management for the gateway: inventory, expiry, self-signed, internal CA,
Let's Encrypt (certbot webroot) and import. Private keys are written with mode 0600.
Issuing and importing run in the privileged agent; inventory is read-only."""

from __future__ import annotations

import datetime as dt
import os
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from nexus_core import runner, validation
from nexus_core.errors import DependencyMissingError, NexusError, ValidationError
from nexus_core.gateway.model import ROUTE_ID_RE, is_non_public_name

LETSENCRYPT_LIVE = Path(os.environ.get("NEXUSOS_LETSENCRYPT_LIVE", "/etc/letsencrypt/live"))
WARN_DAYS = 30
CRITICAL_DAYS = 7


class Certificate(BaseModel):
    name: str
    source: Literal["self-signed", "internal-ca", "letsencrypt", "imported", "unknown"]
    subject: str
    issuer: str
    sans: list[str]
    not_after: str
    days_left: int
    status: Literal["ok", "warning", "critical", "expired"]
    path: str


def _openssl() -> str:
    if runner.which("openssl") is None:
        raise DependencyMissingError("openssl not found", hint="sudo apt install openssl")
    return "openssl"


def inspect_pem(cert: Path) -> tuple[str, str, list[str], dt.datetime]:
    result = runner.run(
        [
            _openssl(),
            "x509",
            "-in",
            str(cert),
            "-noout",
            "-subject",
            "-issuer",
            "-enddate",
            "-ext",
            "subjectAltName",
            "-nameopt",
            "RFC2253",
        ],
        timeout=10,
    )
    if not result.ok:
        raise ValidationError(f"{cert} is not a readable PEM certificate")
    subject = issuer = ""
    sans: list[str] = []
    not_after = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("subject="):
            subject = line[8:]
        elif line.startswith("issuer="):
            issuer = line[7:]
        elif line.startswith("notAfter="):
            not_after = dt.datetime.strptime(line[9:].replace("  ", " "), "%b %d %H:%M:%S %Y %Z").replace(tzinfo=dt.UTC)
        elif "DNS:" in line or "IP Address:" in line:
            sans = [s.strip().split(":", 1)[1] for s in line.split(",")]
    if not_after is None:
        raise ValidationError(f"{cert}: no expiry date")
    return subject, issuer, sans, not_after


def _status(days: int) -> str:
    if days < 0:
        return "expired"
    if days < CRITICAL_DAYS:
        return "critical"
    if days < WARN_DAYS:
        return "warning"
    return "ok"


def inventory(gateway_dir: Path) -> list[Certificate]:
    certs: list[Certificate] = []
    now = dt.datetime.now(dt.UTC)
    sources: list[tuple[str, Path, str]] = []
    for d in sorted((gateway_dir / "certificates").glob("*")) if (gateway_dir / "certificates").exists() else []:
        marker = d / "source"
        kind = marker.read_text().strip() if marker.exists() else "unknown"
        sources.append((d.name, d / "fullchain.pem", kind))
    for d in sorted(LETSENCRYPT_LIVE.glob("*")) if LETSENCRYPT_LIVE.exists() else []:
        if (d / "fullchain.pem").exists():
            sources.append((d.name, d / "fullchain.pem", "letsencrypt"))
    for name, pem, kind in sources:
        try:
            subject, issuer, sans, not_after = inspect_pem(pem)
        except (ValidationError, PermissionError):
            continue
        days = (not_after - now).days
        source = kind if kind in {"self-signed", "internal-ca", "letsencrypt", "imported"} else "unknown"
        certs.append(
            Certificate(
                name=name,
                source=source,
                subject=subject,
                issuer=issuer,
                sans=sans,
                not_after=not_after.isoformat(),
                days_left=days,
                status=_status(days),
                path=str(pem),
            )
        )
    return certs


def _cert_dir(gateway_dir: Path, name: str) -> Path:
    if not ROUTE_ID_RE.match(name) and not all(validation.HOST_LABEL_RE.match(p) for p in name.split(".")):
        raise ValidationError(f"invalid certificate name {name!r}")
    return gateway_dir / "certificates" / name


def _install(gateway_dir: Path, name: str, cert_pem: Path, key_pem: Path, source: str) -> Path:
    target = _cert_dir(gateway_dir, name)
    target.mkdir(mode=0o755, parents=True, exist_ok=True)
    shutil.copyfile(cert_pem, target / "fullchain.pem")
    os.chmod(target / "fullchain.pem", 0o644)
    fd = os.open(target / "privkey.pem", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(key_pem.read_bytes())
    os.chmod(target / "privkey.pem", 0o600)
    (target / "source").write_text(source + "\n")
    return target


def _san_arg(hostnames: list[str]) -> str:
    return "subjectAltName=" + ",".join(f"DNS:{validation.hostname(h, allow_wildcard=True)}" for h in hostnames)


def issue_self_signed(gateway_dir: Path, name: str, hostnames: list[str], days: int = 397) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        key, crt = Path(tmp) / "key.pem", Path(tmp) / "crt.pem"
        result = runner.run(
            [
                _openssl(),
                "req",
                "-x509",
                "-newkey",
                "ec",
                "-pkeyopt",
                "ec_paramgen_curve:prime256v1",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(crt),
                "-days",
                str(days),
                "-subj",
                f"/CN={hostnames[0]}",
                "-addext",
                _san_arg(hostnames),
            ],
            timeout=60,
        )
        if not result.ok:
            raise NexusError("certificate generation failed", hint=runner.first_line(result.stderr))
        return _install(gateway_dir, name, crt, key, "self-signed")


def ensure_ca(gateway_dir: Path) -> Path:
    ca = gateway_dir / "ca"
    ca.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not (ca / "ca.crt").exists():
        result = runner.run(
            [
                _openssl(),
                "req",
                "-x509",
                "-newkey",
                "ec",
                "-pkeyopt",
                "ec_paramgen_curve:prime256v1",
                "-nodes",
                "-keyout",
                str(ca / "ca.key"),
                "-out",
                str(ca / "ca.crt"),
                "-days",
                "3650",
                "-subj",
                "/CN=NexusOS Gateway Internal CA/O=NexusOS",
                "-addext",
                "basicConstraints=critical,CA:TRUE,pathlen:0",
                "-addext",
                "keyUsage=critical,keyCertSign,cRLSign",
            ],
            timeout=60,
        )
        if not result.ok:
            raise NexusError("internal CA creation failed", hint=runner.first_line(result.stderr))
        os.chmod(ca / "ca.key", 0o600)
        os.chmod(ca / "ca.crt", 0o644)
    return ca / "ca.crt"


def issue_internal(gateway_dir: Path, name: str, hostnames: list[str], days: int = 397) -> Path:
    ca_crt = ensure_ca(gateway_dir)
    ca_key = gateway_dir / "ca" / "ca.key"
    with tempfile.TemporaryDirectory() as tmp:
        key, csr, crt, ext = (Path(tmp) / n for n in ("key.pem", "req.csr", "crt.pem", "ext.cnf"))
        ext.write_text(_san_arg(hostnames) + "\nextendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n")
        steps = [
            [
                _openssl(),
                "req",
                "-new",
                "-newkey",
                "ec",
                "-pkeyopt",
                "ec_paramgen_curve:prime256v1",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(csr),
                "-subj",
                f"/CN={hostnames[0]}",
            ],
            [
                _openssl(),
                "x509",
                "-req",
                "-in",
                str(csr),
                "-CA",
                str(ca_crt),
                "-CAkey",
                str(ca_key),
                "-CAcreateserial",
                "-out",
                str(crt),
                "-days",
                str(days),
                "-extfile",
                str(ext),
            ],
        ]
        for cmd in steps:
            result = runner.run(cmd, timeout=60)
            if not result.ok:
                raise NexusError("internal certificate issuance failed", hint=runner.first_line(result.stderr))
        chain = Path(tmp) / "chain.pem"
        chain.write_text(crt.read_text() + ca_crt.read_text())
        return _install(gateway_dir, name, chain, key, "internal-ca")


def import_certificate(gateway_dir: Path, name: str, cert_file: Path, key_file: Path) -> Path:
    inspect_pem(cert_file)
    pub_cert = runner.run([_openssl(), "x509", "-in", str(cert_file), "-noout", "-pubkey"], timeout=10)
    pub_key = runner.run([_openssl(), "pkey", "-in", str(key_file), "-pubout"], timeout=10)
    if not (pub_cert.ok and pub_key.ok) or pub_cert.stdout.strip() != pub_key.stdout.strip():
        raise ValidationError("the private key does not match the certificate")
    return _install(gateway_dir, name, cert_file, key_file, "imported")


def letsencrypt_command(gateway_dir: Path, hostname: str, email: str, staging: bool = False) -> list[str]:
    hostname = validation.hostname(hostname)
    if is_non_public_name(hostname):
        raise ValidationError(f"{hostname} is not a public DNS name; Let's Encrypt cannot issue certificates for it")
    if not validation.single_line(email, max_len=254) or "@" not in email or " " in email:
        raise ValidationError("a valid contact e-mail is required for Let's Encrypt")
    cmd = [
        "certbot",
        "certonly",
        "--webroot",
        "-w",
        str(gateway_dir / "acme"),
        "-d",
        hostname,
        "--non-interactive",
        "--agree-tos",
        "-m",
        email,
        "--keep-until-expiring",
        "--deploy-hook",
        "systemctl reload nginx",
    ]
    if staging:
        cmd.append("--staging")
    return cmd


def issue_letsencrypt(gateway_dir: Path, hostname: str, email: str, staging: bool = False) -> None:
    if runner.which("certbot") is None:
        raise DependencyMissingError("certbot not found", hint="sudo apt install certbot")
    result = runner.run(letsencrypt_command(gateway_dir, hostname, email, staging), timeout=300)
    if not result.ok:
        raise NexusError(
            "Let's Encrypt issuance failed",
            hint=runner.first_line(result.stderr) or "check DNS and that port 80 is reachable",
        )


def renew_due(gateway_dir: Path, days: int = WARN_DAYS) -> list[str]:
    """Re-issue internal/self-signed certificates expiring within *days*. certbot renews its own via its timer."""
    renewed = []
    for cert in inventory(gateway_dir):
        if cert.days_left >= days or cert.source not in ("internal-ca", "self-signed"):
            continue
        hosts = cert.sans or [cert.name]
        (issue_internal if cert.source == "internal-ca" else issue_self_signed)(gateway_dir, cert.name, hosts)
        renewed.append(cert.name)
    return renewed
