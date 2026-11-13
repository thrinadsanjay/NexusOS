"""APT preview helpers. Only simulations run here; real changes happen in commands after confirmation."""

from __future__ import annotations

import re
import time
from pathlib import Path

from nexus_core import runner
from nexus_core.errors import DependencyMissingError, NexusError
from nexus_core.models import UpgradablePackage

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


# =====================================================================================
# Software Center backend (v0.2): catalogue, search, details, plans, history, repos.
# Everything below is unprivileged. Changes are executed by the management agent
# (nexus_core.agent_client) after the user has seen the exact plan.
# =====================================================================================

import gzip  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
from typing import Literal  # noqa: E402

from pydantic import BaseModel, Field  # noqa: E402

from nexus_core import paths, validation  # noqa: E402

DPKG_LOCKS = (
    Path("/var/lib/dpkg/lock-frontend"),
    Path("/var/lib/dpkg/lock"),
    Path("/var/lib/apt/lists/lock"),
    Path("/var/cache/apt/archives/lock"),
)
HISTORY_DIR = Path(os.environ.get("NEXUSOS_APT_LOG_DIR", "/var/log/apt"))
SOURCES_DIR = Path(os.environ.get("NEXUSOS_APT_SOURCES_DIR", "/etc/apt/sources.list.d"))
Operation = Literal["install", "remove", "purge", "upgrade", "update", "full-upgrade"]


class CatalogEntry(BaseModel):
    name: str
    section: str = ""
    summary: str = ""
    installed_version: str | None = None


class PackageDetails(BaseModel):
    name: str
    version: str | None = None
    installed_version: str | None = None
    candidate_version: str | None = None
    section: str | None = None
    maintainer: str | None = None
    homepage: str | None = None
    installed_size_kib: int | None = None
    download_size_bytes: int | None = None
    depends: list[str] = Field(default_factory=list)
    recommends: list[str] = Field(default_factory=list)
    description: str = ""
    origin: str | None = None
    essential: bool = False


class PlannedChange(BaseModel):
    action: Literal["install", "upgrade", "remove", "purge", "reinstall"]
    name: str
    old_version: str | None = None
    new_version: str | None = None


class OperationPlan(BaseModel):
    operation: Operation
    requested: list[str]
    changes: list[PlannedChange]
    command: list[str]
    destructive: bool
    warnings: list[str] = Field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for c in self.changes:
            counts[c.action] = counts.get(c.action, 0) + 1
        return counts


class LockStatus(BaseModel):
    locked: bool
    holder_pid: int | None = None
    holder_name: str | None = None
    lock_file: str | None = None


class HistoryEntry(BaseModel):
    start: str
    end: str | None = None
    command: str | None = None
    requested_by: str | None = None
    install: list[str] = Field(default_factory=list)
    upgrade: list[str] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)
    purge: list[str] = Field(default_factory=list)
    error: str | None = None


class Repository(BaseModel):
    file: str
    format: Literal["deb822", "one-line"]
    types: list[str]
    uris: list[str]
    suites: list[str]
    components: list[str]
    signed_by: str | None = None
    enabled: bool = True
    managed_by_nexusos: bool = False


# --------------------------------------------------------------------- catalogue
APT_HELPER = Path("/usr/lib/apt/apt-helper")


def _package_lists() -> list[Path]:
    """Package index files, plain or compressed (minimal images keep them compressed)."""
    return sorted(APT_LISTS.glob("*_Packages*")) if APT_LISTS.exists() else []


def _list_lines(path: Path):
    """Yield lines of an index file; compressed files are decoded by APT's own helper."""
    import subprocess

    if path.suffix in (".lz4", ".gz", ".xz", ".zst", ".bz2"):
        with subprocess.Popen(
            [str(APT_HELPER), "cat-file", str(path)],
            stdout=subprocess.PIPE,
            text=True,
            errors="replace",
        ) as proc:
            if proc.stdout is not None:
                yield from proc.stdout
    else:
        with path.open(encoding="utf-8", errors="replace") as handle:
            yield from handle


def _lists_signature() -> str:
    files = _package_lists()
    return "|".join(f"{p.name}:{int(p.stat().st_mtime)}" for p in files)


def installed_versions() -> dict[str, str]:
    result = runner.run(["dpkg-query", "-W", "-f", "${Package}\t${Version}\t${db:Status-Abbrev}\n"], timeout=30)
    out = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[2].startswith("ii"):
            out[parts[0]] = parts[1]
    return out


def catalog(refresh: bool = False) -> list[CatalogEntry]:
    """All packages known to APT (name, section, summary), cached per package-list state."""
    cache = paths.data_dir() / "cache" / "apt-catalog.json"
    signature = _lists_signature()
    if not refresh and cache.exists():
        try:
            data = json.loads(cache.read_text())
            if data.get("signature") == signature:
                entries = data["entries"]
                return _with_installed([CatalogEntry(**e) for e in entries])
        except (ValueError, KeyError):
            pass
    entries: dict[str, CatalogEntry] = {}
    for plist in _package_lists():
        name = section = summary = ""
        for line in _list_lines(plist):
            if line.startswith("Package: "):
                name = line[9:].strip()
            elif line.startswith("Section: "):
                section = line[9:].strip()
            elif line.startswith("Description: "):
                summary = line[13:].strip()
            elif line == "\n" and name:
                entries.setdefault(name, CatalogEntry(name=name, section=section, summary=summary))
                name = section = summary = ""
        if name:
            entries.setdefault(name, CatalogEntry(name=name, section=section, summary=summary))
    ordered = sorted(entries.values(), key=lambda e: e.name)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps({"signature": signature, "entries": [e.model_dump(exclude={"installed_version"}) for e in ordered]})
    )
    return _with_installed(ordered)


def _with_installed(entries: list[CatalogEntry]) -> list[CatalogEntry]:
    installed = installed_versions()
    for e in entries:
        e.installed_version = installed.get(e.name)
    return entries


def search(term: str, limit: int = 200, section: str | None = None) -> list[CatalogEntry]:
    """Search names and summaries. Exact and prefix name matches rank first."""
    term = validation.single_line(term, max_len=100, field="search term").strip().lower()
    entries = catalog()
    if section:
        entries = [e for e in entries if e.section.split("/")[-1] == section]
    if not term:
        return entries[:limit]
    scored = []
    for e in entries:
        name = e.name.lower()
        if name == term:
            score = 0
        elif name.startswith(term):
            score = 1
        elif term in name:
            score = 2
        elif term in e.summary.lower():
            score = 3
        else:
            continue
        scored.append((score, len(name), e))
    return [e for _, _, e in sorted(scored, key=lambda t: (t[0], t[1], t[2].name))[:limit]]


def sections() -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for e in catalog():
        key = e.section.split("/")[-1] or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items())


def _parse_stanza(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    key = None
    for line in text.splitlines():
        if line.startswith((" ", "\t")) and key:
            fields[key] += "\n" + line[1:]
        elif ":" in line:
            key, _, value = line.partition(":")
            fields[key] = value.strip()
    return fields


def _dep_names(field: str) -> list[str]:
    names = []
    for group in field.split(","):
        alt = group.strip().split("|")[0].strip()
        if alt:
            names.append(alt.split()[0].split(":")[0])
    return names


def details(name: str) -> PackageDetails:
    validation.package_name(name)
    show = runner.run(["apt-cache", "show", "--no-all-versions", name], timeout=20)
    if not show.ok or not show.stdout.strip():
        raise NexusError(f"package {name!r} not found", hint="refresh package indexes or check the name")
    fields = _parse_stanza(show.stdout.split("\n\n")[0])
    policy = runner.run(["apt-cache", "policy", name], timeout=20).stdout
    installed = candidate = origin = None
    for line in policy.splitlines():
        stripped = line.strip()
        if stripped.startswith("Installed:"):
            installed = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Candidate:"):
            candidate = stripped.split(":", 1)[1].strip()
        elif origin is None and stripped[:3].isdigit() and " " in stripped and "http" in stripped:
            origin = " ".join(stripped.split()[1:3])
    desc = fields.get("Description", fields.get("Description-en", ""))
    return PackageDetails(
        name=name,
        version=fields.get("Version"),
        installed_version=None if installed in (None, "(none)") else installed,
        candidate_version=None if candidate in (None, "(none)") else candidate,
        section=fields.get("Section"),
        maintainer=fields.get("Maintainer"),
        homepage=fields.get("Homepage"),
        installed_size_kib=int(fields["Installed-Size"]) if fields.get("Installed-Size", "").isdigit() else None,
        download_size_bytes=int(fields["Size"]) if fields.get("Size", "").isdigit() else None,
        depends=_dep_names(fields.get("Depends", "")) + _dep_names(fields.get("Pre-Depends", "")),
        recommends=_dep_names(fields.get("Recommends", "")),
        description=desc,
        origin=origin,
        essential=fields.get("Essential", "no") == "yes",
    )


def reverse_dependencies(name: str, limit: int = 100) -> list[str]:
    validation.package_name(name)
    result = runner.run(["apt-cache", "rdepends", "--installed", name], timeout=20)
    names = [ln.strip().lstrip("|") for ln in result.stdout.splitlines()[2:] if ln.strip()]
    return sorted(set(names))[:limit]


def installed_packages() -> list[CatalogEntry]:
    result = runner.run(
        ["dpkg-query", "-W", "-f", "${Package}\t${Version}\t${Section}\t${binary:Summary}\t${db:Status-Abbrev}\n"],
        timeout=30,
    )
    out = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 5 and parts[4].startswith("ii"):
            out.append(CatalogEntry(name=parts[0], installed_version=parts[1], section=parts[2], summary=parts[3]))
    return out


def installed_applications() -> list[CatalogEntry]:
    """Installed packages that ship a desktop launcher (what users think of as 'applications')."""
    desktop_files = [str(p) for p in Path("/usr/share/applications").glob("*.desktop")]
    if not desktop_files:
        return []
    owners: set[str] = set()
    for i in range(0, len(desktop_files), 200):
        result = runner.run(["dpkg-query", "-S", *desktop_files[i : i + 200]], timeout=30)
        for line in result.stdout.splitlines():
            owners.update(p.strip().split(":")[0] for p in line.split(":", 1)[0].split(","))
    return [p for p in installed_packages() if p.name in owners]


# --------------------------------------------------------------------- plans
_REMV_RE = re.compile(r"^(?P<act>Remv|Purg) (?P<name>\S+)(?: \[(?P<old>[^\]]+)\])?")

OP_ARGS: dict[str, list[str]] = {
    "install": ["install"],
    "remove": ["remove"],
    "purge": ["purge"],
    "upgrade": ["upgrade"],
    "full-upgrade": ["full-upgrade"],
}


def build_command(operation: Operation, names: list[str]) -> list[str]:
    """The exact apt-get command the agent will run (shown to the user before execution)."""
    if operation == "update":
        return ["apt-get", "update"]
    base = ["apt-get", "-y", "-o", "DPkg::Lock::Timeout=0", *OP_ARGS[operation]]
    if operation in ("install", "remove", "purge"):
        base += ["--", *validation.package_names(names)]
    return base


def parse_plan_output(output: str) -> list[PlannedChange]:
    changes: list[PlannedChange] = []
    for line in output.splitlines():
        line = line.strip()
        m = _INST_RE.match(line)
        if m:
            action = "upgrade" if m["old"] else "install"
            if m["old"] and m["old"] == m["new"]:
                action = "reinstall"
            changes.append(PlannedChange(action=action, name=m["name"], old_version=m["old"], new_version=m["new"]))
            continue
        m = _REMV_RE.match(line)
        if m:
            changes.append(
                PlannedChange(action="purge" if m["act"] == "Purg" else "remove", name=m["name"], old_version=m["old"])
            )
    return changes


def plan(operation: Operation, names: list[str] | None = None) -> OperationPlan:
    """Simulate an operation with ``apt-get --simulate`` (unprivileged) and describe every change."""
    require_apt()
    names = names or []
    command = build_command(operation, names)
    if operation == "update":
        return OperationPlan(operation=operation, requested=[], changes=[], command=command, destructive=False)
    sim = ["apt-get", "--simulate", "-o", "Debug::NoLocking=1", *OP_ARGS[operation]]
    if names:
        sim += ["--", *validation.package_names(names)]
    result = runner.run(sim, timeout=120)
    if not result.ok:
        message = runner.first_line(result.stderr) or "simulation failed"
        if "Unable to locate package" in result.stderr or "has no installation candidate" in result.stderr:
            raise NexusError(f"package not available: {message}", hint="search the catalogue or refresh indexes")
        raise NexusError(f"APT cannot plan this {operation}: {message}")
    changes = parse_plan_output(result.stdout)
    removed = [c for c in changes if c.action in ("remove", "purge")]
    unrequested_removals = [c.name for c in removed if c.name not in names]
    warnings = []
    if unrequested_removals:
        warnings.append("also removes: " + ", ".join(unrequested_removals[:20]))
    if operation == "purge":
        warnings.append("purge deletes the packages' system-wide configuration files")
    return OperationPlan(
        operation=operation,
        requested=names,
        changes=changes,
        command=command,
        destructive=bool(removed) or operation in ("remove", "purge"),
        warnings=warnings,
    )


# --------------------------------------------------------------------- locks
def lock_status(locks_file: Path = Path("/proc/locks")) -> LockStatus:
    """Detect a running package manager from /proc/locks (works without root)."""
    inodes = {}
    for lock in DPKG_LOCKS:
        try:
            st = lock.stat()
            inodes[(os.major(st.st_dev), os.minor(st.st_dev), st.st_ino)] = lock
        except OSError:
            continue
    try:
        text = locks_file.read_text()
    except OSError:
        return LockStatus(locked=False)
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 6 or "->" in parts:
            continue
        try:
            pid = int(parts[4])
            major, minor, inode = parts[5].split(":")
            key = (int(major, 16), int(minor, 16), int(inode))
        except ValueError:
            continue
        if key in inodes:
            name = Path(f"/proc/{pid}/comm").read_text().strip() if Path(f"/proc/{pid}/comm").exists() else None
            return LockStatus(locked=True, holder_pid=pid, holder_name=name, lock_file=str(inodes[key]))
    return LockStatus(locked=False)


# --------------------------------------------------------------------- history
def _history_files() -> list[Path]:
    files = sorted(HISTORY_DIR.glob("history.log.*.gz"), key=lambda p: int(p.name.split(".")[2]), reverse=True)
    if (HISTORY_DIR / "history.log.1").exists():
        files.append(HISTORY_DIR / "history.log.1")
    files.append(HISTORY_DIR / "history.log")
    return [f for f in files if f.exists()]


def _split_pkgs(value: str) -> list[str]:
    # "foo:amd64 (1.0, 1.1), bar:amd64 (2.0, automatic)"
    return [m.group(1) for m in re.finditer(r"([a-z0-9][a-z0-9+.\-]+)(?::\w+)? \(", value)]


def history(limit: int = 100) -> list[HistoryEntry]:
    entries: list[HistoryEntry] = []
    for path in _history_files():
        try:
            if path.suffix == ".gz":
                with gzip.open(path, "rt", errors="replace") as handle:
                    text = handle.read()
            else:
                text = path.read_text(errors="replace")
        except OSError:
            continue
        for block in text.strip().split("\n\n"):
            fields = dict(line.split(": ", 1) for line in block.strip().splitlines() if ": " in line)
            if "Start-Date" not in fields:
                continue
            entries.append(
                HistoryEntry(
                    start=fields["Start-Date"],
                    end=fields.get("End-Date"),
                    command=fields.get("Commandline"),
                    requested_by=fields.get("Requested-By"),
                    install=_split_pkgs(fields.get("Install", "")),
                    upgrade=_split_pkgs(fields.get("Upgrade", "")),
                    remove=_split_pkgs(fields.get("Remove", "")),
                    purge=_split_pkgs(fields.get("Purge", "")),
                    error=fields.get("Error"),
                )
            )
    return list(reversed(entries))[:limit]


# --------------------------------------------------------------------- repositories
def repositories(sources_dir: Path = SOURCES_DIR) -> list[Repository]:
    repos: list[Repository] = []
    candidates = sorted(sources_dir.glob("*.sources")) + sorted(sources_dir.glob("*.list"))
    legacy = sources_dir.parent / "sources.list"
    if legacy.exists():
        candidates.append(legacy)
    for path in candidates:
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        managed = path.name.startswith("nexusos-")
        if path.suffix == ".sources":
            for stanza in text.split("\n\n"):
                fields = _parse_stanza("\n".join(ln for ln in stanza.splitlines() if not ln.startswith("#")))
                if "URIs" not in fields:
                    continue
                repos.append(
                    Repository(
                        file=str(path),
                        format="deb822",
                        types=fields.get("Types", "deb").split(),
                        uris=fields["URIs"].split(),
                        suites=fields.get("Suites", "").split(),
                        components=fields.get("Components", "").split(),
                        signed_by=fields.get("Signed-By"),
                        enabled=fields.get("Enabled", "yes").lower() != "no",
                        managed_by_nexusos=managed,
                    )
                )
        else:
            for raw in text.splitlines():
                line = raw.strip()
                enabled = not line.startswith("#")
                line = line.lstrip("#").strip()
                if not line.startswith(("deb ", "deb-src ")):
                    continue
                signed = re.search(r"signed-by=([^\s\]]+)", line)
                line = re.sub(r"\[[^\]]*\]\s*", "", line)
                parts = line.split()
                if len(parts) < 3:
                    continue
                repos.append(
                    Repository(
                        file=str(path),
                        format="one-line",
                        types=[parts[0]],
                        uris=[parts[1]],
                        suites=[parts[2]],
                        components=parts[3:],
                        signed_by=signed.group(1) if signed else None,
                        enabled=enabled,
                        managed_by_nexusos=managed,
                    )
                )
    return repos


REPO_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,40}$")
SUITE_RE = re.compile(r"^[A-Za-z0-9._\-/]{1,64}$")
KEYRING_DIRS = (Path("/etc/apt/keyrings"), Path("/usr/share/keyrings"))
ARCHIVE_HTTP_ALLOWED = ("archive.ubuntu.com", "security.ubuntu.com", "ports.ubuntu.com")


def validate_repository(name: str, uri: str, suites: list[str], components: list[str], signed_by: str) -> str:
    """Validate a NexusOS-managed repository definition; returns the deb822 text to install."""
    if not REPO_NAME_RE.match(name or ""):
        raise validation.ValidationError("repository name must be 2-41 chars of a-z, 0-9 and '-'")
    import httpx

    url = httpx.URL(uri)
    host = (url.host or "").lower()
    if url.scheme == "http" and not any(host == h or host.endswith("." + h) for h in ARCHIVE_HTTP_ALLOWED):
        raise validation.ValidationError("third-party repositories must use https://")
    if url.scheme not in ("http", "https") or not host or url.userinfo:
        raise validation.ValidationError(f"invalid repository URI: {uri!r}")
    validation.hostname(host)
    for value in [*suites, *components]:
        if not SUITE_RE.match(value):
            raise validation.ValidationError(f"invalid suite/component: {value!r}")
    if not suites:
        raise validation.ValidationError("at least one suite is required")
    key = Path(signed_by)
    if not any(key.parent == d for d in KEYRING_DIRS) or key.suffix not in (".gpg", ".asc", ".pgp"):
        raise validation.ValidationError("Signed-By must be a keyring file in /etc/apt/keyrings or /usr/share/keyrings")
    lines = [
        f"# Managed by NexusOS ({name}). Remove with the Software Center or `nexus packages repo remove {name}`.",
        "Types: deb",
        f"URIs: {uri}",
        f"Suites: {' '.join(suites)}",
    ]
    if components:
        lines.append(f"Components: {' '.join(components)}")
    lines.append(f"Signed-By: {key}")
    return "\n".join(lines) + "\n"
