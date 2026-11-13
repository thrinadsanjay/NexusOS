"""Detection of developer, infrastructure and cloud command-line tools."""

from __future__ import annotations

import grp
import os
import re
from dataclasses import dataclass
from pathlib import Path

from nexus_core import runner
from nexus_core.models import ToolInfo

_VERSION_RE = re.compile(r"v?(\d+\.\d+(?:\.\d+)?(?:[-+~][0-9A-Za-z.\-+~]*)?)")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    command: str
    version_args: tuple[str, ...]


DEV_TOOLS = (
    ToolSpec("Python", "python3", ("--version",)),
    ToolSpec("pipx", "pipx", ("--version",)),
    ToolSpec("Node.js", "node", ("--version",)),
    ToolSpec("npm", "npm", ("--version",)),
    ToolSpec("Go", "go", ("version",)),
    ToolSpec("Rust", "rustc", ("--version",)),
    ToolSpec("Git", "git", ("--version",)),
    ToolSpec("GCC", "gcc", ("--version",)),
)

CLOUD_TOOLS = (
    ToolSpec("AWS CLI", "aws", ("--version",)),
    ToolSpec("Google Cloud CLI", "gcloud", ("--version",)),
    ToolSpec("Azure CLI", "az", ("--version",)),
    ToolSpec("kubectl", "kubectl", ("version", "--client")),
    ToolSpec("Helm", "helm", ("version", "--short")),
    ToolSpec("Terraform", "terraform", ("version",)),
    ToolSpec("OpenTofu", "tofu", ("version",)),
    ToolSpec("Ansible", "ansible", ("--version",)),
)

# Presence (never contents) of well-known credential/config locations, relative to $HOME.
CLOUD_CONFIG_HINTS = {
    "AWS CLI": ".aws/config",
    "Google Cloud CLI": ".config/gcloud",
    "Azure CLI": ".azure",
    "kubectl": ".kube/config",
}


def extract_version(text: str) -> str | None:
    match = _VERSION_RE.search(text)
    return match.group(1) if match else None


def probe(spec: ToolSpec, timeout: float = 10.0) -> ToolInfo:
    if runner.which(spec.command) is None:
        return ToolInfo(name=spec.name, command=spec.command, available=False)
    result = runner.run([spec.command, *spec.version_args], timeout=timeout)
    version = extract_version(result.stdout + "\n" + result.stderr) if result.found else None
    return ToolInfo(name=spec.name, command=spec.command, available=True, version=version)


def probe_all(specs: tuple[ToolSpec, ...]) -> list[ToolInfo]:
    return [probe(spec) for spec in specs]


def cloud_config_present(name: str, home: Path | None = None) -> bool:
    rel = CLOUD_CONFIG_HINTS.get(name)
    return bool(rel) and ((home or Path.home()) / rel).exists()


def kube_current_context() -> str | None:
    if runner.which("kubectl") is None:
        return None
    result = runner.run(["kubectl", "config", "current-context"], timeout=5)
    return result.stdout.strip() or None if result.ok else None


def user_groups() -> set[str]:
    names = set()
    for gid in os.getgroups():
        try:
            names.add(grp.getgrgid(gid).gr_name)
        except KeyError:
            continue
    return names


def kvm_status(cpuinfo: Path = Path("/proc/cpuinfo"), dev: Path = Path("/dev/kvm")) -> ToolInfo:
    try:
        flags = cpuinfo.read_text(encoding="utf-8")
    except OSError:
        flags = ""
    hw = "vmx" if " vmx" in flags else "svm" if " svm" in flags else None
    if not dev.exists():
        note = "CPU supports virtualisation but /dev/kvm is missing" if hw else "no hardware virtualisation detected"
        return ToolInfo(name="KVM", command=str(dev), available=False, note=note)
    usable = os.access(dev, os.R_OK | os.W_OK)
    return ToolInfo(
        name="KVM",
        command=str(dev),
        available=usable,
        version=hw,
        note=None if usable else "present but not accessible; add your user to the `kvm` group",
    )


def libvirt_status() -> ToolInfo:
    if runner.which("virsh") is None:
        return ToolInfo(
            name="libvirt", command="virsh", available=False, note="install libvirt (infrastructure manifest)"
        )
    for unit in ("virtqemud.socket", "libvirtd.service", "libvirtd.socket"):
        result = runner.run(["systemctl", "is-active", unit], timeout=5)
        if result.stdout.strip() == "active":
            version = runner.run(["virsh", "--version"], timeout=5)
            return ToolInfo(
                name="libvirt", command="virsh", available=True, version=version.stdout.strip() or None, note=unit
            )
    return ToolInfo(name="libvirt", command="virsh", available=False, note="installed but no libvirt daemon is active")
