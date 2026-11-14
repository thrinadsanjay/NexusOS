"""Storage (destructive guards), network, local AI, search/palette, settings, metrics, services."""

from __future__ import annotations

import json
import threading

import httpx
import pytest
from nexus_core import chat, metrics, network, ollama, runner, search, services, settings, storage
from nexus_core.errors import NexusError, ValidationError

LSBLK = {
    "blockdevices": [
        {
            "name": "nvme0n1",
            "path": "/dev/nvme0n1",
            "type": "disk",
            "size": 2000398934016,
            "model": "Samsung 990",
            "serial": "S7XYZ",
            "rota": False,
            "tran": "nvme",
            "mountpoints": [None],
            "children": [
                {
                    "name": "nvme0n1p1",
                    "path": "/dev/nvme0n1p1",
                    "type": "part",
                    "size": 1073741824,
                    "fstype": "vfat",
                    "mountpoints": ["/boot/efi"],
                },
                {
                    "name": "nvme0n1p2",
                    "path": "/dev/nvme0n1p2",
                    "type": "part",
                    "size": 1999000000000,
                    "fstype": "ext4",
                    "mountpoints": ["/"],
                },
            ],
        },
        {
            "name": "sda",
            "path": "/dev/sda",
            "type": "disk",
            "size": 4000787030016,
            "model": "WD Red",
            "serial": "WD-ABC123",
            "rota": True,
            "tran": "sata",
            "mountpoints": [None],
            "children": [
                {
                    "name": "sda1",
                    "path": "/dev/sda1",
                    "type": "part",
                    "size": 4000000000000,
                    "fstype": "ext4",
                    "mountpoints": ["/srv/data"],
                }
            ],
        },
        {
            "name": "sdb",
            "path": "/dev/sdb",
            "type": "disk",
            "size": 64000000000,
            "model": "USB",
            "serial": None,
            "rota": False,
            "tran": "usb",
            "mountpoints": [None],
            "children": [
                {
                    "name": "sdb1",
                    "path": "/dev/sdb1",
                    "type": "part",
                    "size": 63000000000,
                    "fstype": "exfat",
                    "mountpoints": [None],
                }
            ],
        },
    ]
}


@pytest.fixture
def fake_lsblk(monkeypatch):
    calls = []

    def run(argv, timeout=0, env=None):
        calls.append(argv)
        if argv[0] == "lsblk":
            return runner.CommandResult(tuple(argv), 0, json.dumps(LSBLK), "")
        return runner.CommandResult(tuple(argv), 0, "", "")

    monkeypatch.setattr(runner, "run", run)
    monkeypatch.setattr(storage, "swaps", lambda *a: [])
    return calls


def test_inventory_media_types(fake_lsblk):
    devs = {d.path: d for d in storage.devices()}
    assert (
        devs["/dev/nvme0n1"].media == "NVMe SSD" and devs["/dev/sda"].media == "HDD" and devs["/dev/sdb"].media == "SSD"
    )


def test_format_refuses_system_disk_and_mounted(fake_lsblk):
    with pytest.raises(ValidationError, match="system mount points"):
        storage.plan_format("/dev/nvme0n1p2", "ext4")
    with pytest.raises(ValidationError, match="mounted"):
        storage.plan_format("/dev/sda1", "ext4")
    with pytest.raises(ValidationError):
        storage.plan_format("/dev/sdb1; rm -rf /", "ext4")
    with pytest.raises(ValidationError):
        storage.plan_format("/dev/sdb1", "zfs-exotic")


def test_format_requires_typed_token_and_uses_udisks(fake_lsblk):
    plan = storage.plan_format("/dev/sdb1", "ext4", "backup")
    assert plan.confirmation_token == "/dev/sdb1"  # no serial: the device path must be typed
    executed = []
    with pytest.raises(ValidationError):
        storage.execute_format(plan, "yes", executor=lambda argv, timeout=0: executed.append(argv))
    assert executed == []
    storage.execute_format(
        plan, "/dev/sdb1", executor=lambda argv, timeout=0: executed.append(argv) or runner.CommandResult((), 0, "", "")
    )
    argv = executed[0]
    assert (
        argv[:2] == ["gdbus", "call"]
        and "org.freedesktop.UDisks2.Block.Format" in argv
        and "mkfs" not in " ".join(argv)
    )


def test_format_detects_device_change(fake_lsblk, monkeypatch):
    plan = storage.plan_format("/dev/sdb1", "ext4")
    plan.size += 1
    with pytest.raises(ValidationError, match="changed"):
        storage.execute_format(plan, plan.confirmation_token, executor=lambda *a, **k: None)


def test_unmount_refuses_system_mounts(fake_lsblk):
    with pytest.raises(ValidationError):
        storage.unmount("/dev/nvme0n1p2")


def test_smart_without_agent():
    s = storage.smart("/dev/sda")
    assert not s.available and "agent" in s.message


def test_nmcli_parsing_and_static_ip(monkeypatch):
    monkeypatch.setattr(runner, "which", lambda p: f"/usr/bin/{p}")
    out = "Home\\: WiFi:1234-uuid:802-11-wireless:wlp3s0:yes\nWired:5678:802-3-ethernet:--:no\n"
    monkeypatch.setattr(runner, "run", lambda argv, timeout=0, env=None: runner.CommandResult(tuple(argv), 0, out, ""))
    conns = network.connections()
    assert conns[0].name == "Home: WiFi" and conns[0].active and not conns[1].active
    argv = network.static_ipv4_argv(
        network.StaticIPv4(connection="Wired", address="192.168.1.20/24", gateway="192.168.1.1", dns=["1.1.1.1"])
    )
    assert argv[-4:] == ["ipv4.gateway", "192.168.1.1", "ipv4.dns", "1.1.1.1"]
    for bad in (dict(address="192.168.1.20/24", gateway="10.0.0.1"), dict(address="fe80::1/64"), dict(address="x")):
        with pytest.raises((ValidationError, ValueError)):
            network.static_ipv4_argv(network.StaticIPv4(connection="Wired", **bad))


def test_checkpoint_rollback_flow(monkeypatch):
    seen = []

    def run(argv, timeout=0, env=None):
        seen.append(argv)
        if any("CheckpointCreate" in a for a in argv):
            return runner.CommandResult(
                tuple(argv), 0, "(objectpath '/org/freedesktop/NetworkManager/Checkpoint/3',)", ""
            )
        return runner.CommandResult(tuple(argv), 0, "", "")

    monkeypatch.setattr(runner, "run", run)
    monkeypatch.setattr(runner, "which", lambda p: "/usr/bin/" + p)
    path = network.apply_with_checkpoint(["nmcli", "connection", "modify", "id", "Wired"], "Wired", 30)
    assert path.endswith("/3") and "30" in seen[0]
    network.confirm_checkpoint(path)
    assert any("CheckpointDestroy" in a for a in seen[-1])
    with pytest.raises(ValidationError):
        network.confirm_checkpoint("/etc/passwd")


def test_network_without_networkmanager(monkeypatch):
    monkeypatch.setattr(runner, "which", lambda p: None)
    with pytest.raises(NexusError, match="NetworkManager"):
        network.connections()
    with pytest.raises(ValidationError):
        network.diagnose("a;b")


def ollama_transport(events):
    def handler(req: httpx.Request) -> httpx.Response:
        events.append(req.url.path)
        if req.url.path == "/api/show":
            return httpx.Response(
                200,
                json={
                    "details": {"family": "llama"},
                    "model_info": {"llama.context_length": 131072},
                    "capabilities": ["completion"],
                },
            )
        if req.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "m", "size": 4000, "size_vram": 1000}]})
        if req.url.path == "/api/pull":
            return httpx.Response(200, content=b'{"status":"pulling","total":10,"completed":5}\n{"status":"success"}\n')
        if req.url.path == "/api/chat":
            body = json.loads(req.content)
            if body["model"] == "missing:1b":
                return httpx.Response(404, json={"error": "not found"})
            return httpx.Response(
                200, content=b'{"message":{"content":"Hel"}}\n{"message":{"content":"lo"}}\n{"done":true}\n'
            )
        if req.url.path == "/api/delete":
            return httpx.Response(200)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_ollama_model_management():
    calls = []
    t = ollama_transport(calls)
    assert ollama.show("m", "http://127.0.0.1:11434", t).context_length == 131072
    assert ollama.running("http://127.0.0.1:11434", t)[0].mode == "CPU+GPU"
    assert [e["status"] for e in ollama.pull("m", "http://127.0.0.1:11434", t)] == ["pulling", "success"]
    stop = threading.Event()
    stop.set()
    assert list(ollama.pull("m", "http://127.0.0.1:11434", t, cancel=stop)) == []
    ollama.delete("m", "http://127.0.0.1:11434", t)
    with pytest.raises(ValidationError):
        ollama.delete("m; rm", "http://127.0.0.1:11434", t)


def test_chat_streaming_and_errors():
    t = ollama_transport([])
    chunks = list(
        ollama.chat_stream(
            "m", [{"role": "user", "content": "hi"}], ollama.ChatOptions(temperature=0.2), "http://127.0.0.1:11434", t
        )
    )
    assert "".join(chunks) == "Hello"
    with pytest.raises(NexusError, match="not installed"):
        list(ollama.chat_stream("missing:1b", [{"role": "user", "content": "x"}], None, "http://127.0.0.1:11434", t))
    with pytest.raises(ValidationError):
        list(ollama.chat_stream("m", [{"role": "root", "content": "x"}], None, "http://127.0.0.1:11434", t))


def test_chat_store_context_is_bounded(monkeypatch):
    monkeypatch.setattr(chat, "MAX_CONTEXT_MESSAGES", 4)
    cid = chat.create("m", "You are terse.")
    for i in range(10):
        chat.add_message(cid, "user" if i % 2 == 0 else "assistant", f"msg {i}")
    ctx = chat.context(cid)
    assert ctx[0] == {"role": "system", "content": "You are terse."} and len(ctx) == 5
    assert chat.conversations()[0].title == "msg 0"
    chat.clear(cid)
    assert chat.messages(cid) == []


def test_palette_finds_actions_without_running_them():
    results = search.search("restart nginx")
    top = results[0]
    assert top.kind == "action" and top.target == "service.restart:nginx.service" and top.requires_confirmation
    assert any(r.kind == "setting" and r.target == "kcm_kscreen" for r in search.search("resolution"))
    assert any(r.kind == "page" and r.target == "gateway" for r in search.search("gateway"))

    def broken(q):
        raise RuntimeError("docker down")

    assert search.search("terminal", providers=[broken])
    assert search.search("x") == []


def test_palette_ssh_profile_provider():
    from nexus_core.ssh import profiles

    profiles.save(profiles.SSHProfile(name="cloud-server", host="203.0.113.10", user="ops", group="Cloud servers"))
    assert any(
        r.kind == "ssh" and r.title == "cloud-server" for r in search.search("cloud server", [search.ssh_provider])
    )


def test_settings_catalog_and_kcm_guard():
    assert len({e.id for e in settings.CATALOG}) == len(settings.CATALOG)
    with pytest.raises(ValidationError):
        settings.open_kcm("kcm_evil; rm -rf")
    with pytest.raises(ValidationError):
        settings.set_hostname("bad host name")


def test_services_only_control_approved_units():
    with pytest.raises(ValidationError):
        services.control("sshd-keygen.service", "start")
    with pytest.raises(ValidationError):
        services.control("../../x.service", "start")


def test_metrics_from_fake_proc_and_sys(tmp_path, monkeypatch):
    proc, sys_ = tmp_path / "proc", tmp_path / "sys"
    (proc / "net").mkdir(parents=True)
    (proc / "1").mkdir()
    (proc / "1" / "status").write_text("Name:\tinit\nState:\tS\nUid:\t0 0 0 0\nVmRSS:\t2048 kB\n")
    (proc / "meminfo").write_text("MemTotal: 1000 kB\nMemAvailable: 250 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n")
    (proc / "uptime").write_text("100.0 50.0\n")
    hw = sys_ / "class" / "hwmon" / "hwmon0"
    hw.mkdir(parents=True)
    (hw / "name").write_text("k10temp\n")
    (hw / "temp1_input").write_text("55125\n")
    (hw / "temp1_label").write_text("Tctl\n")
    monkeypatch.setattr(metrics, "PROC", proc)
    monkeypatch.setattr(metrics, "SYS", sys_)
    s = metrics.Sampler()
    (proc / "stat").write_text("cpu  100 0 100 800 0 0 0 0\ncpu0 100 0 100 800 0 0 0 0\n")
    (proc / "net" / "dev").write_text("h\nh\n  eth0: 1000 0 0 0 0 0 0 0 2000 0\n")
    first = s.snapshot()
    assert first.cpu_percent is None  # no fake value before a second sample
    (proc / "stat").write_text("cpu  200 0 200 900 0 0 0 0\ncpu0 200 0 200 900 0 0 0 0\n")
    (proc / "net" / "dev").write_text("h\nh\n  eth0: 3000 0 0 0 0 0 0 0 2000 0\n")
    second = s.snapshot()
    assert second.cpu_percent == 66.7 and second.temperatures[0].celsius == 55.125
    assert second.net[0].rx_bytes_per_s > 0 and second.memory_total == 1024000
    assert metrics.top_processes()[0].name == "init"


def test_metrics_without_sensors(tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "SYS", tmp_path)
    temps, note = metrics.temperatures()
    assert temps == [] and "no temperature sensors" in note


# ---- regressions found on a real Plasma 6.6 / systemd 259 session -----------------------------


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        ("LoadState=loaded\nActiveState=active\n", "active"),  # systemd's own order
        ("ActiveState=failed\nLoadState=loaded\n", "failed"),
        ("LoadState=not-found\nActiveState=inactive\n", "not-found"),
        ("", "unknown"),
    ],
)
def test_service_state_parsing_is_order_independent(monkeypatch, stdout, expected):
    monkeypatch.setattr(
        runner, "run", lambda argv, timeout=0, env=None: runner.CommandResult(tuple(argv), 0, stdout, "")
    )
    assert services.is_active("nginx.service") == expected


def test_disk_usage_skips_file_bind_mounts_and_duplicates(monkeypatch, tmp_path):
    out = (
        "Mounted on Filesystem Type 1B-blocks Used Avail\n"
        f"{tmp_path} /dev/sda1 ext4 100 40 60\n"
        "/etc/hosts /dev/sda1 ext4 100 40 60\n"
        f"{tmp_path} /dev/sda1 ext4 100 40 60\n"
    )
    monkeypatch.setattr(runner, "run", lambda argv, timeout=0, env=None: runner.CommandResult(tuple(argv), 0, out, ""))
    assert [u.mount for u in storage.usage()] == [str(tmp_path)]


def test_places_do_not_repeat_home(monkeypatch, tmp_path):
    from nexus_core import files

    monkeypatch.setenv("HOME", str(tmp_path))
    xbel = tmp_path / ".local" / "share" / "user-places.xbel"
    xbel.parent.mkdir(parents=True)
    xbel.write_text(
        '<?xml version="1.0"?><xbel>'
        f'<bookmark href="file://{tmp_path}/"><title>Home</title></bookmark>'
        f'<bookmark href="file://{tmp_path}/Projects"><title>Projects</title></bookmark>'
        "</xbel>"
    )
    assert [p.title for p in files.places()] == ["Home", "Projects"]


def test_settings_catalog_marks_missing_kcms(monkeypatch):
    monkeypatch.setattr(settings, "installed_kcms", lambda: {"kcm_colors", "kcm_users"})
    entries = {e.kcm: e for e in settings.catalog() if e.kcm}
    assert entries["kcm_colors"].available
    assert not entries["kcm_kscreen"].available and entries["kcm_kscreen"].package == "kscreen"
    from nexus_core.errors import DependencyMissingError

    with pytest.raises(DependencyMissingError) as exc:
        settings.open_kcm("kcm_bluetooth")
    assert "bluedevil" in (exc.value.hint or "")
    # Without any Plasma installed (CI) nothing is marked missing.
    monkeypatch.setattr(settings, "installed_kcms", set)
    assert all(e.available for e in settings.catalog())
