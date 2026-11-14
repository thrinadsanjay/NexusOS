"""Storage: disk inventory (lsblk), usage, SMART (via agent), mount/unmount (UDisks2),
and guarded destructive operations (format) through UDisks2 D-Bus.

Destructive operations are never automatic. They require: a plan describing the exact
device (model, serial, size), refusal for system/mounted disks, a typed confirmation
token that must equal the device's serial (or path when no serial exists), and
UDisks2/polkit administrator authorization.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nexus_core import agent_client, runner
from nexus_core.errors import DependencyMissingError, NexusError, ValidationError

SYSTEM_MOUNTS = {"/", "/boot", "/boot/efi", "/home", "/usr", "/var", "/etc", "/opt", "/srv"}
DEVICE_RE = re.compile(
    r"^/dev/(sd[a-z]{1,2}[0-9]*|nvme[0-9]+n[0-9]+(p[0-9]+)?|vd[a-z]{1,2}[0-9]*|mmcblk[0-9]+(p[0-9]+)?|loop[0-9]+)$"
)
FILESYSTEMS = ("ext4", "xfs", "btrfs", "vfat", "exfat", "ntfs")


class BlockDevice(BaseModel):
    path: str
    name: str
    type: str
    size: int
    model: str | None = None
    serial: str | None = None
    rotational: bool | None = None
    transport: str | None = None
    fstype: str | None = None
    label: str | None = None
    uuid: str | None = None
    mountpoints: list[str] = Field(default_factory=list)
    fs_size: int | None = None
    fs_used: int | None = None
    children: list[BlockDevice] = Field(default_factory=list)

    @property
    def media(self) -> str:
        if self.transport == "nvme":
            return "NVMe SSD"
        if self.rotational is True:
            return "HDD"
        if self.rotational is False:
            return "SSD"
        return "unknown"

    def all_mountpoints(self) -> list[str]:
        mps = list(self.mountpoints)
        for child in self.children:
            mps += child.all_mountpoints()
        return mps


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _parse(dev: dict) -> BlockDevice:
    return BlockDevice(
        path=dev.get("path") or f"/dev/{dev.get('name')}",
        name=dev.get("name", "?"),
        type=dev.get("type", "?"),
        size=_int(dev.get("size")) or 0,
        model=(dev.get("model") or "").strip() or None,
        serial=(dev.get("serial") or "").strip() or None,
        rotational=bool(dev["rota"]) if dev.get("rota") is not None else None,
        transport=dev.get("tran"),
        fstype=dev.get("fstype"),
        label=dev.get("label"),
        uuid=dev.get("uuid"),
        mountpoints=[m for m in (dev.get("mountpoints") or []) if m],
        fs_size=_int(dev.get("fssize")),
        fs_used=_int(dev.get("fsused")),
        children=[_parse(c) for c in dev.get("children") or []],
    )


def devices() -> list[BlockDevice]:
    result = runner.run(
        [
            "lsblk",
            "-J",
            "-b",
            "-o",
            "NAME,PATH,TYPE,SIZE,MODEL,SERIAL,ROTA,TRAN,FSTYPE,LABEL,UUID,MOUNTPOINTS,FSSIZE,FSUSED",
        ],
        timeout=15,
    )
    if not result.ok:
        raise DependencyMissingError("lsblk failed", hint=runner.first_line(result.stderr))
    return [_parse(d) for d in json.loads(result.stdout).get("blockdevices", [])]


def find(path: str, devs: list[BlockDevice] | None = None) -> tuple[BlockDevice, BlockDevice]:
    """Return (device, top-level disk) for a device path."""
    for disk in devs if devs is not None else devices():
        stack = [disk]
        while stack:
            dev = stack.pop()
            if dev.path == path:
                return dev, disk
            stack += dev.children
    raise ValidationError(f"no such block device: {path}")


class Swap(BaseModel):
    device: str
    type: str
    size_kib: int
    used_kib: int
    priority: int


def swaps(proc_swaps: Path = Path("/proc/swaps")) -> list[Swap]:
    out = []
    lines = proc_swaps.read_text().splitlines()[1:] if proc_swaps.exists() else []
    for line in lines:
        p = line.split()
        if len(p) >= 5:
            out.append(Swap(device=p[0], type=p[1], size_kib=int(p[2]), used_kib=int(p[3]), priority=int(p[4])))
    return out


class Usage(BaseModel):
    mount: str
    source: str
    fstype: str
    size: int
    used: int
    available: int


def usage() -> list[Usage]:
    result = runner.run(
        [
            "df",
            "-B1",
            "--output=target,source,fstype,size,used,avail",
            "-x",
            "tmpfs",
            "-x",
            "devtmpfs",
            "-x",
            "squashfs",
            "-x",
            "overlay",
        ],
        timeout=15,
    )
    out: list[Usage] = []
    seen: set[str] = set()
    for line in result.stdout.splitlines()[1:]:
        p = line.split()
        # Skip bind-mounted files (/etc/hosts in containers) and repeated mount points.
        if len(p) == 6 and p[3].isdigit() and p[0] not in seen and os.path.isdir(p[0]):
            seen.add(p[0])
            out.append(Usage(mount=p[0], source=p[1], fstype=p[2], size=int(p[3]), used=int(p[4]), available=int(p[5])))
    return out


class SmartSummary(BaseModel):
    device: str
    available: bool
    passed: bool | None = None
    temperature_c: float | None = None
    power_on_hours: int | None = None
    percentage_used: int | None = None
    message: str = ""


def smart(device: str) -> SmartSummary:
    """SMART health via the management agent (smartctl needs root)."""
    if not DEVICE_RE.match(device):
        raise ValidationError(f"invalid device {device!r}")
    from nexus_core import privilege

    try:
        data = agent_client.call("storage.smart", {"device": device}, label=f"Read SMART health of {device}")
        data = data.get("smart") or {}
    except DependencyMissingError as exc:
        return SmartSummary(device=device, available=False, message=exc.message)
    except (privilege.AccessDeniedError, privilege.AuthCancelledError) as exc:
        return SmartSummary(device=device, available=False, message=exc.message)
    if not data:
        return SmartSummary(device=device, available=False, message="SMART not supported by this device")
    nvme = data.get("nvme_smart_health_information_log") or {}
    return SmartSummary(
        device=device,
        available=True,
        passed=(data.get("smart_status") or {}).get("passed"),
        temperature_c=(data.get("temperature") or {}).get("current"),
        power_on_hours=(data.get("power_on_time") or {}).get("hours"),
        percentage_used=nvme.get("percentage_used"),
    )


def disk_temperatures(sys_block: Path = Path("/sys/block")) -> dict[str, float]:
    """Unprivileged NVMe/drivetemp temperatures from hwmon, where the kernel exposes them."""
    out = {}
    for dev in sys_block.glob("*"):
        for hwmon in (dev / "device").glob("hwmon/hwmon*/temp1_input") if (dev / "device").exists() else []:
            try:
                out[dev.name] = int(hwmon.read_text()) / 1000
            except (OSError, ValueError):
                continue
    return out


# --------------------------------------------------------------------- mount / unmount (UDisks2 + polkit)
def mount(device: str) -> str:
    if not DEVICE_RE.match(device):
        raise ValidationError(f"invalid device {device!r}")
    result = runner.run(["udisksctl", "mount", "-b", device, "--no-user-interaction"], timeout=60)
    if not result.ok:
        result = runner.run(["udisksctl", "mount", "-b", device], timeout=120)
    if not result.ok:
        raise NexusError(f"could not mount {device}", hint=runner.first_line(result.stderr))
    return result.stdout.strip()


def unmount(device: str) -> None:
    dev, _ = find(device)
    if set(dev.mountpoints) & SYSTEM_MOUNTS:
        raise ValidationError(f"{device} holds a system mount point and cannot be unmounted here")
    result = runner.run(["udisksctl", "unmount", "-b", device], timeout=120)
    if not result.ok:
        raise NexusError(f"could not unmount {device}", hint=runner.first_line(result.stderr))


# --------------------------------------------------------------------- destructive operations
class DestructivePlan(BaseModel):
    operation: Literal["format"]
    device: str
    disk: str
    model: str | None
    serial: str | None
    size: int
    filesystem: str
    label: str
    confirmation_token: str
    warnings: list[str]


def plan_format(
    device: str, filesystem: str, label: str = "", devs: list[BlockDevice] | None = None
) -> DestructivePlan:
    if not DEVICE_RE.match(device):
        raise ValidationError(f"invalid device {device!r}")
    if filesystem not in FILESYSTEMS:
        raise ValidationError(f"unsupported filesystem {filesystem!r}")
    if label and not re.fullmatch(r"[A-Za-z0-9_\-]{1,16}", label):
        raise ValidationError("label: up to 16 letters, digits, '_' or '-'")
    dev, disk = find(device, devs)
    disk_mounts = set(disk.all_mountpoints())
    if disk_mounts & SYSTEM_MOUNTS:
        raise ValidationError(
            f"{disk.path} contains system mount points ({', '.join(sorted(disk_mounts & SYSTEM_MOUNTS))}); "
            "formatting it from a running system is not allowed"
        )
    if dev.all_mountpoints():
        raise ValidationError(f"{device} is mounted at {', '.join(dev.all_mountpoints())}; unmount it first")
    if any(s.device.startswith(dev.path) for s in swaps()):
        raise ValidationError(f"{device} is in use as swap")
    token = disk.serial or dev.path
    warnings = [f"ALL DATA on {dev.path} ({dev.size // 10**9} GB {disk.model or ''}) will be destroyed."]
    if dev.type == "disk":
        warnings.append("This formats the whole disk without a partition table.")
    return DestructivePlan(
        operation="format",
        device=dev.path,
        disk=disk.path,
        model=disk.model,
        serial=disk.serial,
        size=dev.size,
        filesystem=filesystem,
        label=label,
        confirmation_token=token,
        warnings=warnings,
    )


def udisks_object_path(device: str) -> str:
    return "/org/freedesktop/UDisks2/block_devices/" + Path(device).name.replace("-", "_2d")


def format_argv(plan: DestructivePlan) -> list[str]:
    options = f"{{'label': <'{plan.label}'>, 'erase': <'zero'>}}" if plan.label else "{}"
    return [
        "gdbus",
        "call",
        "--system",
        "--dest",
        "org.freedesktop.UDisks2",
        "--object-path",
        udisks_object_path(plan.device),
        "--method",
        "org.freedesktop.UDisks2.Block.Format",
        plan.filesystem,
        options,
        "--timeout",
        "3600",
    ]


def execute_format(plan: DestructivePlan, typed_confirmation: str, *, executor=runner.run) -> None:
    """Format after re-validating the plan and matching the typed confirmation token.

    UDisks2 asks polkit (org.freedesktop.udisks2.modify-device) for administrator rights.
    """
    if typed_confirmation != plan.confirmation_token:
        raise ValidationError("confirmation does not match the device serial/path; nothing was changed")
    fresh = plan_format(plan.device, plan.filesystem, plan.label)  # re-check: still unmounted, same disk
    if (fresh.serial, fresh.size, fresh.disk) != (plan.serial, plan.size, plan.disk):
        raise ValidationError("the device changed since the plan was made; nothing was changed")
    result = executor(format_argv(plan), timeout=3600)
    if not result.ok:
        raise NexusError(f"formatting {plan.device} failed", hint=runner.first_line(result.stderr))
