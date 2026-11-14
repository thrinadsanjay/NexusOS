"""Hardware inventory and operations dashboard (fixtures stand in for sysfs, udev, lsblk, systemctl, sadf)."""

from __future__ import annotations

import json
import os

import pytest
from nexus_core import dashboard, hardware, packages, runner, storage


def _ok(stdout: str):
    return lambda argv, timeout=0, env=None: runner.CommandResult(tuple(argv), 0, stdout, "")


# ---------------------------------------------------------------------------- CPU
def test_cpu_from_proc_and_cpufreq(tmp_path):
    proc, sys_root = tmp_path / "proc", tmp_path / "sys"
    proc.mkdir()
    (proc / "cpuinfo").write_text(
        "processor\t: 0\nvendor_id\t: AuthenticAMD\nmodel name\t: AMD Ryzen 9 9900X 12-Core Processor\n"
        "cpu MHz\t\t: 4400.000\ncpu cores\t: 12\nflags\t\t: fpu sse svm avx512f\nmicrocode\t: 0xb404023\n\n"
        "processor\t: 1\nvendor_id\t: AuthenticAMD\n"
    )
    freq = sys_root / "devices" / "system" / "cpu" / "cpu0" / "cpufreq"
    freq.mkdir(parents=True)
    (freq / "cpuinfo_max_freq").write_text("5662000\n")
    (freq / "base_frequency").write_text("4400000\n")
    (freq / "scaling_cur_freq").write_text("4700000\n")
    (freq / "scaling_driver").write_text("amd-pstate-epp\n")
    (freq / "energy_performance_preference").write_text("balance_performance\n")
    c = hardware.cpu(sys_root, proc)
    assert c.model == "AMD Ryzen 9 9900X"
    assert (c.vendor, c.virtualization, c.max_mhz, c.base_mhz, c.current_mhz) == ("AMD", "AMD-V", 5662, 4400, 4700)
    assert c.scaling_driver == "amd-pstate-epp" and c.epp == "balance_performance" and c.microcode == "0xb404023"


# ---------------------------------------------------------------------------- memory
UDEV_DMI = {
    "MEMORY_ARRAY_NUM_DEVICES": "4",
    "MEMORY_ARRAY_MAX_CAPACITY": str(192 * 2**30),
    "MEMORY_ARRAY_EC_TYPE": "None",
    "MEMORY_DEVICE_0_PRESENT": "0",
    "MEMORY_DEVICE_0_LOCATOR": "DIMM A1",
    "MEMORY_DEVICE_1_SIZE": str(16 * 2**30),
    "MEMORY_DEVICE_1_LOCATOR": "DIMM A2",
    "MEMORY_DEVICE_1_TYPE": "DDR5",
    "MEMORY_DEVICE_1_SPEED_MTS": "6000",
    "MEMORY_DEVICE_1_CONFIGURED_SPEED_MTS": "6000",
    "MEMORY_DEVICE_1_MANUFACTURER": "Kingston",
    "MEMORY_DEVICE_1_PART_NUMBER": "KF560C30-16",
    "MEMORY_DEVICE_1_CONFIGURED_VOLTAGE": "1350",
    "MEMORY_DEVICE_2_PRESENT": "0",
    "MEMORY_DEVICE_2_LOCATOR": "DIMM B1",
    "MEMORY_DEVICE_3_SIZE": str(16 * 2**30),
    "MEMORY_DEVICE_3_LOCATOR": "DIMM B2",
    "MEMORY_DEVICE_3_TYPE": "DDR5",
    "MEMORY_DEVICE_3_SPEED_MTS": "6000",
    "MEMORY_DEVICE_3_MANUFACTURER": "Kingston",
    "MEMORY_DEVICE_3_PART_NUMBER": "KF560C30-16",
}


def test_memory_modules_from_udev_smbios():
    m = hardware.memory(UDEV_DMI, {"MemTotal": 31 * 2**30})
    assert m.summary == "DDR5-6000 · 2 × 16 GB"
    assert [x.slot for x in m.modules] == ["DIMM A1", "DIMM A2", "DIMM B1", "DIMM B2"]
    assert [x.present for x in m.modules] == [False, True, False, True]
    assert m.modules[1].part_number == "KF560C30-16" and m.modules[1].voltage_mv == 1350
    assert m.slots == 4 and m.ecc is None and m.note is None


def test_memory_without_smbios_says_so():
    m = hardware.memory({}, {"MemTotal": 2**34})
    assert m.modules == [] and m.summary is None and "not exposed" in m.note


# ---------------------------------------------------------------------------- GPU
def _pci_device(root, card, vendor, files):
    dev = root / "devices" / "pci0000:00" / "0000:01:00.0"
    dev.mkdir(parents=True)
    (dev / "vendor").write_text(vendor + "\n")
    for name, value in files.items():
        path = dev / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value + "\n")
    drv = root / "bus" / "pci" / "drivers" / "amdgpu"
    drv.mkdir(parents=True)
    (dev / "driver").symlink_to(drv)
    drm = root / "class" / "drm" / card
    drm.mkdir(parents=True)
    (drm / "device").symlink_to(dev)


def test_amd_gpu_from_sysfs(tmp_path, monkeypatch):
    _pci_device(
        tmp_path,
        "card0",
        "0x1002",
        {
            "mem_info_vram_total": str(16 * 2**30),
            "mem_info_vram_used": str(2**30),
            "gpu_busy_percent": "17",
            "current_link_speed": "16.0 GT/s PCIe",
            "current_link_width": "16",
            "hwmon/hwmon3/temp1_input": "41000",
            "hwmon/hwmon3/power1_average": "38000000",
        },
    )
    calls = []

    def run(argv, timeout=0, env=None):
        calls.append(argv[0])
        if argv[0] == "lspci":
            return runner.CommandResult(tuple(argv), 0, "Vendor:\tAMD\nDevice:\tNavi 48 [Radeon RX 9070 XT]\n", "")
        return runner.CommandResult(tuple(argv), 127, "", "not found")

    monkeypatch.setattr(runner, "run", run)
    g = hardware.gpus(tmp_path)[0]
    assert (g.name, g.vendor, g.driver, g.integrated) == ("Radeon RX 9070 XT", "AMD", "amdgpu", False)
    assert (g.link, g.busy_percent, g.temperature_c, g.power_w) == ("PCIe 4.0 ×16", 17, 41.0, 38.0)
    assert "nvidia-smi" in calls


def test_nvidia_gpu_from_nvidia_smi(tmp_path, monkeypatch):
    out = "NVIDIA GeForce RTX 4060, 8188, 2100, 18, 41, 38.20, 115.00, 580.95.05, 4, 8, 00000000:01:00.0\n"
    monkeypatch.setattr(
        runner,
        "run",
        lambda argv, timeout=0, env=None: runner.CommandResult(
            tuple(argv), 0, out if argv[0] == "nvidia-smi" else "", ""
        ),
    )
    g = hardware.gpus(tmp_path)[0]
    assert g.name == "NVIDIA GeForce RTX 4060" and g.link == "PCIe 4.0 ×8" and g.driver_version == "580.95.05"
    assert g.vram_total_bytes == 8188 * 2**20 and g.power_limit_w == 115.0


# ---------------------------------------------------------------------------- drives
def test_drives_with_nvme_link_and_mounts(tmp_path, monkeypatch):
    dev = tmp_path / "devices" / "pci" / "nvme0"
    dev.mkdir(parents=True)
    (dev / "current_link_speed").write_text("16.0 GT/s PCIe\n")
    (dev / "current_link_width").write_text("4\n")
    (tmp_path / "class" / "nvme" / "nvme0").mkdir(parents=True)
    os.symlink(dev, tmp_path / "class" / "nvme" / "nvme0" / "device")
    lsblk = json.dumps(
        {
            "blockdevices": [
                {
                    "name": "nvme0n1",
                    "path": "/dev/nvme0n1",
                    "model": "WD_BLACK SN850X 1000GB",
                    "size": 1000204886016,
                    "tran": "nvme",
                    "rota": False,
                    "type": "disk",
                    "rev": "620361WD",
                    "mountpoints": [None],
                    "children": [
                        {"name": "nvme0n1p2", "mountpoints": ["/"]},
                        {"name": "nvme0n1p1", "mountpoints": ["/boot/efi"]},
                    ],
                },
                {
                    "name": "sda",
                    "path": "/dev/sda",
                    "model": "Samsung SSD 870",
                    "size": 2000398934016,
                    "tran": "sata",
                    "rota": False,
                    "type": "disk",
                    "mountpoints": ["/mnt/data"],
                },
                {"name": "loop0", "type": "loop", "size": 1},
                {"name": "zram0", "type": "disk", "size": 1},
            ]
        }
    )
    monkeypatch.setattr(storage, "disk_temperatures", lambda _p: {})
    d = hardware.drives(tmp_path, lsblk)
    assert [x.name for x in d] == ["nvme0n1", "sda"]
    assert (d[0].kind, d[0].link, d[0].mounts) == ("NVMe", "PCIe 4.0 ×4", ["/", "/boot/efi"])
    assert d[1].kind == "SATA SSD" and d[1].mounts == ["/mnt/data"]


# ---------------------------------------------------------------------------- dashboard sources
def test_services_summary(monkeypatch):
    units = [
        {"unit": "nginx.service", "load": "loaded", "active": "failed", "sub": "failed"},
        {"unit": "ssh.service", "load": "loaded", "active": "active", "sub": "running"},
        {"unit": "fwupd.service", "load": "loaded", "active": "activating", "sub": "start"},
        {"unit": "gone.service", "load": "not-found", "active": "inactive", "sub": "dead"},
    ]

    def run(argv, timeout=0, env=None):
        return runner.CommandResult(tuple(argv), 0, json.dumps(units) if "list-units" in argv else "degraded\n", "")

    monkeypatch.setattr(runner, "run", run)
    s = dashboard.services_summary()
    assert (s.running, s.failed, s.starting, s.total, s.system_state) == (1, ["nginx.service"], 1, 3, "degraded")


def test_security_updates_are_flagged():
    out = (
        "Inst libssl3t64 [3.5.1-1ubuntu2] (3.5.1-1ubuntu2.1 Ubuntu:26.04/resolute-updates, Ubuntu:26.04/resolute-security [amd64])\n"
        "Inst hello [2.10-3] (2.10-4 Ubuntu:26.04/resolute-updates [amd64])\n"
    )
    pkgs = packages.parse_simulation(out)
    assert [(p.name, p.security) for p in pkgs] == [("libssl3t64", True), ("hello", False)]


def test_backup_timers(monkeypatch):
    now_us = 1_794_600_000 * 1_000_000
    timers = [
        {
            "unit": "restic-backup.timer",
            "activates": "restic-backup.service",
            "last": now_us - 3 * 86400 * 10**6,
            "next": now_us + 3600 * 10**6,
        },
        {"unit": "apt-daily.timer", "activates": "apt-daily.service", "last": now_us, "next": now_us},
    ]

    def run(argv, timeout=0, env=None):
        return runner.CommandResult(tuple(argv), 0, json.dumps(timers) if "list-timers" in argv else "success\n", "")

    monkeypatch.setattr(runner, "run", run)
    b = dashboard.backups()
    assert b.configured and [j["unit"] for j in b.jobs] == ["restic-backup.service"] and b.overdue


def test_sar_history_parsing(tmp_path, monkeypatch):
    import datetime as dt

    day = dt.date.today()
    (tmp_path / f"sa{day:%d}").write_text("binary")
    stamp = dt.datetime.now().replace(microsecond=0)
    doc = {
        "sysstat": {
            "hosts": [
                {
                    "statistics": [
                        {
                            "timestamp": {"date": f"{stamp:%Y-%m-%d}", "time": f"{stamp:%H:%M:%S}", "utc": 0},
                            "cpu-load": [{"cpu": "all", "idle": 75.0}],
                            "memory": {"memused-percent": 40.0},
                            "disk": [{"rkB": 100.0, "wkB": 50.0}],
                            "network": {
                                "net-dev": [
                                    {"iface": "lo", "rxkB": 999, "txkB": 999},
                                    {"iface": "eth0", "rxkB": 10.0, "txkB": 5.0},
                                ]
                            },
                        },
                    ]
                }
            ]
        }
    }
    monkeypatch.setattr(runner, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(runner, "run", _ok(json.dumps(doc)))
    h = dashboard.sar_history(tmp_path)
    assert h.available and h.daily[0]["cpu"] == 25.0 and h.daily[0]["memory"] == 40.0
    assert h.points_24h["disk"][0][1] == 150 * 1024 and h.points_24h["network"][0][1] == 15 * 1024


def test_sar_missing_is_explained(monkeypatch):
    monkeypatch.setattr(runner, "which", lambda name: None)
    assert dashboard.sar_history().reason == "sysstat is not installed"


def test_history_buckets_per_minute():
    h = dashboard.History()
    for i in range(3):
        h.add(600 + i, 10.0 * (i + 1), 50.0, 0, 0)
    h.add(661, 90.0, 60.0, 0, 0)
    assert h.series("cpu") == [(600, 20.0), (660, 90.0)]


def test_attention_orders_and_explains():
    usage = [storage.Usage(mount="/mnt/data", source="/dev/sda1", fstype="ext4", size=1000, used=950, available=50)]
    issues = dashboard.attention(
        services=dashboard.ServiceSummary(failed=["nginx.service"]),
        updates=dashboard.UpdateSummary(total=5, security=2, security_packages=["openssl", "curl"], checked_at="10:00"),
        usage=usage,
        certs=dashboard.CertSummary(expiring=1, next_expiry="app.lab in 12 d"),
        backup=None,
        temperature_c=60,
        memory_percent=40,
    )
    assert [i.severity for i in issues] == ["critical", "warning", "warning", "warning"]
    assert issues[0].page == "settings" and issues[0].intent == "native:services"
    assert any(i.title == "/mnt/data 95 % used" for i in issues)


@pytest.mark.parametrize(
    ("labels", "expected"),
    [([("k10temp Tctl", 61.0), ("nvme Composite", 40.0)], 61.0), ([("coretemp Package id 0", 55.0)], 55.0), ([], None)],
)
def test_cpu_package_temperature(labels, expected):
    from nexus_core.metrics import Temperature

    assert dashboard.cpu_package_temperature([Temperature(label=label, celsius=c) for label, c in labels]) == expected
