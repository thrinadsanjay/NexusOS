"""Hardware inventory for the dashboard: CPU, memory modules, GPUs and drives.

Everything here is readable by an unprivileged user:

* CPU: ``lscpu -J``, ``/proc/cpuinfo`` and cpufreq sysfs;
* memory modules: SMBIOS type 17 as exported by systemd-udev
  (``udevadm info /devices/virtual/dmi/id`` → ``MEMORY_DEVICE_<n>_*``);
* GPUs: DRM sysfs, ``lspci -vmm`` names, amdgpu counters and hwmon,
  ``nvidia-smi`` when the NVIDIA driver is installed;
* drives: ``lsblk``, NVMe PCIe link and SATA link speed from sysfs, hwmon temperature.

SMART wear needs root and is read on request through the admin helper (Storage).
Values a system does not expose are ``None`` and the UI omits them; nothing is guessed.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from pydantic import BaseModel

from nexus_core import runner
from nexus_core.metrics import PROC, SYS, _read

PCI_VENDORS = {"0x1002": "AMD", "0x10de": "NVIDIA", "0x8086": "Intel", "0x1af4": "Virtio", "0x15ad": "VMware"}
PCIE_GEN = {"2.5": "1.0", "5.0": "2.0", "8.0": "3.0", "16.0": "4.0", "32.0": "5.0", "64.0": "6.0"}
INVENTORY_TTL_S = 600


# ---------------------------------------------------------------------------- models
class CpuInfo(BaseModel):
    model: str
    vendor: str | None = None
    architecture: str | None = None
    sockets: int | None = None
    cores: int | None = None
    threads: int | None = None
    base_mhz: float | None = None
    max_mhz: float | None = None
    current_mhz: float | None = None
    cache: dict[str, str] = {}
    virtualization: str | None = None
    scaling_driver: str | None = None
    governor: str | None = None
    epp: str | None = None
    microcode: str | None = None


class MemoryModule(BaseModel):
    slot: str
    present: bool
    size_bytes: int | None = None
    type: str | None = None
    speed_mts: int | None = None
    configured_speed_mts: int | None = None
    manufacturer: str | None = None
    part_number: str | None = None
    form_factor: str | None = None
    voltage_mv: int | None = None
    rank: int | None = None


class MemoryInfo(BaseModel):
    total_bytes: int | None = None
    slots: int | None = None
    max_capacity_bytes: int | None = None
    ecc: str | None = None
    modules: list[MemoryModule] = []
    summary: str | None = None  # "DDR5-6000 · 2 × 16 GB"
    note: str | None = None


class GpuDevice(BaseModel):
    name: str
    vendor: str
    driver: str | None = None
    pci_slot: str | None = None
    integrated: bool = False
    link: str | None = None
    vram_total_bytes: int | None = None
    vram_used_bytes: int | None = None
    busy_percent: float | None = None
    temperature_c: float | None = None
    power_w: float | None = None
    power_limit_w: float | None = None
    driver_version: str | None = None


class Drive(BaseModel):
    name: str
    path: str
    model: str | None = None
    vendor: str | None = None
    size_bytes: int
    kind: str  # NVMe | SATA SSD | HDD | USB | virtual | other
    link: str | None = None
    temperature_c: float | None = None
    mounts: list[str] = []
    firmware: str | None = None


class Inventory(BaseModel):
    cpu: CpuInfo
    memory: MemoryInfo
    gpus: list[GpuDevice]
    drives: list[Drive]


# ---------------------------------------------------------------------------- CPU
def _lscpu() -> dict[str, str]:
    result = runner.run(["lscpu", "-J"], timeout=5, env={"LC_ALL": "C"})
    if not result.ok:
        return {}
    try:
        rows = json.loads(result.stdout).get("lscpu", [])
    except ValueError:
        return {}
    out: dict[str, str] = {}

    def walk(entries: list[dict]) -> None:
        for e in entries:
            out[e.get("field", "").rstrip(":")] = e.get("data") or ""
            walk(e.get("children") or [])

    walk(rows)
    return out


def _int(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(value) if value.isdigit() else None


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _mhz_from_khz(path: Path) -> float | None:
    khz = _int(_read(path))
    return round(khz / 1000, 0) if khz else None


def cpu(sys_root: Path | None = None, proc_root: Path | None = None) -> CpuInfo:
    sys_root, proc_root = sys_root or SYS, proc_root or PROC
    info = _lscpu() if sys_root == SYS else {}
    cpuinfo = _read(proc_root / "cpuinfo") or ""
    first = cpuinfo.split("\n\n", 1)[0]
    fields = {k.strip(): v.strip() for k, _, v in (line.partition(":") for line in first.splitlines()) if v}
    flags = set(fields.get("flags", "").split())
    model = info.get("Model name") or fields.get("model name") or "Unknown CPU"
    model = re.sub(r"\s+", " ", re.sub(r"\((R|TM)\)|\b\d+-Core Processor\b|\bCPU\b(?= @)", "", model)).strip()
    threads = _int(info.get("CPU(s)")) or (cpuinfo.count("processor\t:") or None)
    per_core = _int(info.get("Thread(s) per core")) or 1
    sockets = _int(info.get("Socket(s)")) or 1
    cores = (_int(info.get("Core(s) per socket")) or 0) * sockets or (_int(fields.get("cpu cores")) or None)
    if cores is None and threads:
        cores = threads // per_core
    freq = sys_root / "devices" / "system" / "cpu" / "cpu0" / "cpufreq"
    cur = []
    for f in (sys_root / "devices" / "system" / "cpu").glob("cpu[0-9]*/cpufreq/scaling_cur_freq"):
        v = _int(_read(f))
        if v:
            cur.append(v)
    cache = {}
    for level in ("L1d", "L1i", "L2", "L3"):
        raw = info.get(f"{level} cache") or info.get(f"{level}")
        if raw:
            cache[level] = raw.split(" (")[0]
    return CpuInfo(
        model=model,
        vendor={"AuthenticAMD": "AMD", "GenuineIntel": "Intel"}.get(fields.get("vendor_id", ""), info.get("Vendor ID")),
        architecture=info.get("Architecture") or os.uname().machine,
        sockets=sockets,
        cores=cores,
        threads=threads,
        base_mhz=_mhz_from_khz(freq / "base_frequency") or _mhz_from_khz(freq / "cpuinfo_min_freq"),
        max_mhz=_mhz_from_khz(freq / "cpuinfo_max_freq") or _float(info.get("CPU max MHz")),
        current_mhz=round(sum(cur) / len(cur) / 1000, 0) if cur else _float(fields.get("cpu MHz")),
        cache=cache,
        virtualization="AMD-V" if "svm" in flags else "VT-x" if "vmx" in flags else None,
        scaling_driver=(_read(freq / "scaling_driver") or "").strip() or None,
        governor=(_read(freq / "scaling_governor") or "").strip() or None,
        epp=(_read(freq / "energy_performance_preference") or "").strip() or None,
        microcode=fields.get("microcode"),
    )


# ---------------------------------------------------------------------------- memory
def _udev_dmi() -> dict[str, str]:
    result = runner.run(["udevadm", "info", "--query=property", "--path=/devices/virtual/dmi/id"], timeout=5)
    if not result.ok:
        return {}
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def memory(props: dict[str, str] | None = None, meminfo: dict[str, int] | None = None) -> MemoryInfo:
    from nexus_core.metrics import meminfo as read_meminfo

    props = _udev_dmi() if props is None else props
    mem = read_meminfo() if meminfo is None else meminfo
    count = _int(props.get("MEMORY_ARRAY_NUM_DEVICES"))
    indexes = sorted({int(m.group(1)) for k in props if (m := re.match(r"MEMORY_DEVICE_(\d+)_", k))})
    modules = []
    for i in indexes:
        g = lambda key, i=i: props.get(f"MEMORY_DEVICE_{i}_{key}")  # noqa: E731
        size = _int(g("SIZE"))
        present = g("PRESENT") != "0" and bool(size)
        part = (g("PART_NUMBER") or "").strip() or None
        maker = (g("MANUFACTURER") or "").strip() or None
        if maker and maker.lower() in ("unknown", "not specified", "undefined"):
            maker = None
        modules.append(
            MemoryModule(
                slot=(g("LOCATOR") or g("BANK_LOCATOR") or f"slot {i}").strip(),
                present=present,
                size_bytes=size if present else None,
                type=(g("TYPE") or None) if present else None,
                speed_mts=_int(g("SPEED_MTS")),
                configured_speed_mts=_int(g("CONFIGURED_SPEED_MTS")),
                manufacturer=maker,
                part_number=part if part and part.lower() not in ("unknown", "not specified") else None,
                form_factor=g("FORM_FACTOR"),
                voltage_mv=_int(g("CONFIGURED_VOLTAGE")),
                rank=_int(g("RANK")),
            )
        )
    installed = [m for m in modules if m.present]
    summary = None
    if installed:
        kinds = {m.type for m in installed if m.type}
        speed = max((m.configured_speed_mts or m.speed_mts or 0) for m in installed) or None
        sizes = {m.size_bytes for m in installed}
        kind = "/".join(sorted(kinds)) if kinds else "RAM"
        head = f"{kind}-{speed}" if speed else kind
        count_part = f"{len(installed)} × {_gb(next(iter(sizes)))}" if len(sizes) == 1 else f"{len(installed)} modules"
        summary = f"{head} · {count_part}"
    ecc = props.get("MEMORY_ARRAY_EC_TYPE")
    return MemoryInfo(
        total_bytes=mem.get("MemTotal"),
        slots=count or (len(modules) or None),
        max_capacity_bytes=_int(props.get("MEMORY_ARRAY_MAX_CAPACITY")),
        ecc=None if ecc in (None, "None", "Unknown") else ecc,
        modules=modules,
        summary=summary,
        note=None if modules else "module details are not exposed by this system's firmware (SMBIOS)",
    )


def _gb(n: int | None) -> str:
    if not n:
        return "?"
    gb = n / 2**30
    return f"{gb:.0f} GB" if gb >= 1 else f"{n // 2**20} MB"


# ---------------------------------------------------------------------------- GPUs
def _lspci_name(slot: str) -> str | None:
    result = runner.run(["lspci", "-vmm", "-s", slot], timeout=5)
    if not result.ok:
        return None
    fields = dict(line.split(":\t", 1) for line in result.stdout.splitlines() if ":\t" in line)
    return fields.get("Device")


def _link(device: Path) -> str | None:
    speed = (_read(device / "current_link_speed") or "").strip()
    width = (_read(device / "current_link_width") or "").strip()
    if not speed or not width or width == "0":
        return None
    gts = speed.split()[0]
    gen = PCIE_GEN.get(gts if "." in gts else f"{gts}.0")
    return f"PCIe {gen} ×{width}" if gen else f"{speed} ×{width}"


def _hwmon_value(device: Path, pattern: str, scale: float) -> float | None:
    for f in sorted(device.glob(f"hwmon/hwmon*/{pattern}")):
        v = _int(_read(f))
        if v is not None:
            return round(v / scale, 1)
    return None


def gpus(sys_root: Path | None = None, *, names: bool = True) -> list[GpuDevice]:
    sys_root = sys_root or SYS
    found: list[GpuDevice] = []
    for card in sorted((sys_root / "class" / "drm").glob("card[0-9]")):
        device = card / "device"
        vendor_id = (_read(device / "vendor") or "").strip()
        if not vendor_id:
            continue
        slot = os.path.basename(os.path.realpath(device))
        driver = os.path.basename(os.readlink(device / "driver")) if (device / "driver").exists() else None
        vendor = PCI_VENDORS.get(vendor_id, vendor_id)
        name = None
        if names and re.match(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$", slot):
            name = _lspci_name(slot)
        vram = _int(_read(device / "mem_info_vram_total"))
        integrated = vendor == "Intel" or (vendor == "AMD" and vram is not None and vram <= 2**30)
        found.append(
            GpuDevice(
                name=_clean_gpu_name(name, vendor) or f"{vendor} GPU",
                vendor=vendor,
                driver=driver,
                pci_slot=slot,
                integrated=integrated,
                link=_link(device),
                vram_total_bytes=vram,
                vram_used_bytes=_int(_read(device / "mem_info_vram_used")),
                busy_percent=_int(_read(device / "gpu_busy_percent")),
                temperature_c=_hwmon_value(device, "temp1_input", 1000),
                power_w=_hwmon_value(device, "power1_average", 1_000_000)
                or _hwmon_value(device, "power1_input", 1_000_000),
                power_limit_w=_hwmon_value(device, "power1_cap", 1_000_000),
            )
        )
    smi = runner.run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw,"
            "power.limit,driver_version,pcie.link.gen.current,pcie.link.width.current,pci.bus_id",
            "--format=csv,noheader,nounits",
        ],
        timeout=5,
    )
    if smi.ok and smi.stdout.strip():
        found = [g for g in found if g.vendor != "NVIDIA"]
        for line in smi.stdout.strip().splitlines():
            p = [x.strip() for x in line.split(",")]
            if len(p) < 11:
                continue

            def num(x: str) -> float | None:
                try:
                    return float(x)
                except ValueError:
                    return None

            found.append(
                GpuDevice(
                    name=_clean_gpu_name(p[0], "NVIDIA") or p[0],
                    vendor="NVIDIA",
                    driver="nvidia",
                    driver_version=p[7],
                    pci_slot=p[10].lower()[-12:],
                    link=f"PCIe {p[8]}.0 ×{p[9]}" if p[8].isdigit() and p[9].isdigit() else None,
                    vram_total_bytes=int(num(p[1]) * 2**20) if num(p[1]) else None,
                    vram_used_bytes=int(num(p[2]) * 2**20) if num(p[2]) is not None else None,
                    busy_percent=num(p[3]),
                    temperature_c=num(p[4]),
                    power_w=num(p[5]),
                    power_limit_w=num(p[6]),
                )
            )
    found.sort(key=lambda g: (g.integrated, g.name))  # discrete first
    return found


def _clean_gpu_name(name: str | None, vendor: str) -> str | None:
    """lspci "AD107 [GeForce RTX 4060]" → "NVIDIA GeForce RTX 4060"."""
    if not name:
        return None
    m = re.search(r"\[([^\]]+)\]\s*$", name)
    short = (m.group(1) if m else name).strip()
    if vendor == "NVIDIA" and not short.startswith("NVIDIA"):
        return f"NVIDIA {short}"
    return short


# ---------------------------------------------------------------------------- drives
def _sata_link(sys_root: Path, name: str) -> str | None:
    real = os.path.realpath(sys_root / "block" / name)
    m = re.search(r"/ata(\d+)/", real)
    if not m:
        return None
    spd = (_read(sys_root / "class" / "ata_link" / f"link{m.group(1)}" / "sata_spd") or "").strip()
    return f"SATA {spd.replace('Gbps', 'Gb/s')}" if spd and spd != "<unknown>" else None


def drives(sys_root: Path | None = None, lsblk_json: str | None = None) -> list[Drive]:
    from nexus_core.storage import disk_temperatures

    sys_root = sys_root or SYS
    if lsblk_json is None:
        result = runner.run(
            ["lsblk", "-J", "-b", "-o", "NAME,PATH,MODEL,VENDOR,SIZE,TRAN,ROTA,TYPE,REV,MOUNTPOINTS"], timeout=10
        )
        lsblk_json = result.stdout if result.ok else '{"blockdevices": []}'
    try:
        devices = json.loads(lsblk_json).get("blockdevices", [])
    except ValueError:
        devices = []
    temps = disk_temperatures(sys_root / "block") if sys_root == SYS else {}
    out = []
    for dev in devices:
        if dev.get("type") != "disk" or str(dev.get("name", "")).startswith(("loop", "zram", "ram", "sr")):
            continue
        name = dev["name"]
        tran = (dev.get("tran") or "").lower()
        rota = dev.get("rota") in (True, "1", 1)
        if tran == "nvme" or name.startswith("nvme"):
            kind = "NVMe"
            ctrl = re.sub(r"n\d+$", "", name)
            link = _link(sys_root / "class" / "nvme" / ctrl / "device")
        elif tran == "usb":
            kind, link = "USB", None
        elif tran in ("virtio", "") and name.startswith("vd"):
            kind, link = "virtual", None
        else:
            kind = "HDD" if rota else "SATA SSD" if tran == "sata" else "SSD"
            link = _sata_link(sys_root, name)
        mounts: list[str] = []

        def collect(node: dict, acc: list[str] = mounts) -> None:
            for m in node.get("mountpoints") or []:
                # skip swap and file bind mounts (/etc/hosts in containers)
                if m and not m.startswith("[SWAP]") and not os.path.isfile(m):
                    acc.append(m)
            for child in node.get("children") or []:
                collect(child, acc)

        collect(dev)
        model = (dev.get("model") or "").strip() or None
        vendor = (dev.get("vendor") or "").strip() or None
        out.append(
            Drive(
                name=name,
                path=dev.get("path") or f"/dev/{name}",
                model=model,
                vendor=None if vendor and vendor.startswith("0x") else vendor,
                size_bytes=int(dev.get("size") or 0),
                kind=kind,
                link=link,
                temperature_c=temps.get(name),
                mounts=sorted(set(mounts), key=lambda m: (len(m), m)),
                firmware=(dev.get("rev") or "").strip() or None,
            )
        )
    return out


# ---------------------------------------------------------------------------- inventory
_cache: tuple[float, Inventory] | None = None


def inventory(refresh: bool = False) -> Inventory:
    """Static inventory, cached for 10 minutes (live GPU values come from :func:`gpus`)."""
    global _cache
    if _cache and not refresh and time.monotonic() - _cache[0] < INVENTORY_TTL_S:
        return _cache[1]
    inv = Inventory(cpu=cpu(), memory=memory(), gpus=gpus(), drives=drives())
    _cache = (time.monotonic(), inv)
    return inv
