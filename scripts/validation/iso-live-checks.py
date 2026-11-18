#!/usr/bin/env python3
"""Log in to a booted NexusOS live image on its serial console and check the session.

Used by iso-boot-smoke.sh inside the test container. Connects to QEMU's serial socket,
logs in as the passwordless live account and runs read-only checks. Prints PASS/FAIL lines
and writes the raw console transcript to OUT/live-console.log.

usage: iso-live-checks.py SERIAL_SOCKET OUT_DIR MINUTES
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import time

sock_path, out_dir, minutes = sys.argv[1], sys.argv[2], float(sys.argv[3])
deadline = time.time() + minutes * 60
ANSI = re.compile(rb"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)|\x1bP[^\x1b]*\x1b\\")

s = socket.socket(socket.AF_UNIX)
for _ in range(120):
    try:
        s.connect(sock_path)
        break
    except OSError:
        time.sleep(1)
s.settimeout(1)
log = open(f"{out_dir}/live-console.log", "wb")  # noqa: SIM115
buf = b""
fails = 0


def read_until(pattern: bytes, timeout: float) -> bool:
    global buf
    end = min(time.time() + timeout, deadline)
    while time.time() < end:
        try:
            data = s.recv(65536)
            if data:
                buf += data
                log.write(data)
                log.flush()
        except TimeoutError:
            pass
        if re.search(pattern, ANSI.sub(b"", buf[-6000:])):
            return True
    return False


def run(cmd: str, timeout: float = 300) -> str:
    """Run a shell command; return its output (between our markers)."""
    global buf
    buf = b""
    # The terminal echoes the typed line, so the markers are split by quotes there ("@@""B")
    # and only appear joined in the command's output.
    s.sendall(f'echo "@@""B"; {cmd}; echo "@@""E"\r'.encode())
    read_until(rb"\n@@E\r?\n", timeout)
    text = ANSI.sub(b"", buf).decode(errors="replace")
    m = re.search(r"\n@@B\r?\n(.*?)\r?\n?@@E", text, re.S)
    return m.group(1).strip() if m else ""


def check(ok: bool, message: str) -> None:
    global fails
    print(("PASS  " if ok else "FAIL  ") + message, flush=True)
    fails += 0 if ok else 1


if not read_until(rb"login:\s*$", minutes * 60):
    check(False, "no login prompt on the serial console")
    sys.exit(1)
time.sleep(3)
s.sendall(b"nexus-live\r")
check(read_until(rb"nexus-live@\S+:~\$ $", 180), "live account logs in on the console (no password, live session only)")
s.sendall(b"export TERM=dumb SYSTEMD_PAGER= PAGER=cat; stty cols 200\r")
read_until(rb"\$ $", 30)

# Wait for the graphical session (software emulation is slow).
plasma = False
while time.time() < deadline:
    if run("pgrep -u nexus-live -x plasmashell >/dev/null && echo PLASMA-UP || echo waiting").endswith("PLASMA-UP"):
        plasma = True
        break
    time.sleep(20)
state = run("systemctl is-system-running")
check(state in ("running", "degraded"), f"systemd boot finished ({state})")
check(run("systemctl is-active sddm") == "active", "SDDM is running")
sessions = run('loginctl list-sessions --no-legend | awk \'$3=="nexus-live" && $4=="seat0" {print $1}\' | head -1')
stype = run(f"loginctl show-session {sessions or 'self'} -p Type --value") if sessions else ""
check(stype == "wayland", f"autologin graphical session for nexus-live is Wayland ({stype or 'none'})")
check(plasma, "Plasma shell started (plasmashell)")
check(run("pgrep -u nexus-live -x kwin_wayland >/dev/null && echo yes") == "yes", "KWin Wayland compositor running")
failed = run("systemctl --failed --no-legend --plain | awk '{print $1}' | tr '\\n' ' '")
check(failed == "", f"no failed system units ({failed or 'none'})")
check("NexusOS Engineering Edition" in run("grep PRETTY_NAME /etc/os-release"), "os-release identifies NexusOS")
check("Crafted by Sanjay" in run("nexus version"), "nexus CLI works in the live session")
check(run("command -v nexus-center nexusos-install calamares | wc -l") == "3", "Command Center and installer present")
check(run("test -x ~/Desktop/nexusos-install.desktop && echo yes") == "yes", "'Install NexusOS' on the live desktop")
check(
    run("readlink -f /usr/share/plymouth/themes/default.plymouth").endswith("nexusos.plymouth"),
    "NexusOS boot splash active",
)
check("NexusOS" in run("head -1 /etc/issue"), "console login banner shows NexusOS")


def screendump(name: str) -> None:
    """Screenshot of the VM display through QEMU's monitor (no guest cooperation needed)."""
    qmp = os.environ.get("QMP_SOCKET")
    if not qmp:
        return
    q = socket.socket(socket.AF_UNIX)
    q.connect(qmp)
    q.settimeout(10)
    q.recv(4096)
    for cmd in (
        {"execute": "qmp_capabilities"},
        {"execute": "screendump", "arguments": {"filename": f"/tmp/{name}.ppm"}},
    ):
        q.sendall(json.dumps(cmd).encode() + b"\n")
        time.sleep(1)
        q.recv(4096)
    q.close()
    time.sleep(1)
    try:
        from PIL import Image

        Image.open(f"/tmp/{name}.ppm").save(f"{out_dir}/{name}.png")
        print(f"      screenshot {name}.png", flush=True)
    except Exception as exc:  # screenshots are evidence, not a check
        print(f"      screenshot {name} failed: {exc}", flush=True)


if os.environ.get("LAYOUT_TEST"):
    # Desktop: System Status panel and expanded launcher through the applets' global shortcuts.
    bus = "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus"
    widget = (
        bus + " qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "
        "'var r=[]; panels().forEach(function(p){ p.widgets(\"%s\").forEach(function(w){ r.push(w.id) }) }); print(r[r.length-1]);'"
    )
    activate = (
        bus
        + " qdbus6 org.kde.kglobalaccel /component/plasmashell org.kde.kglobalaccel.Component.invokeShortcut 'activate widget %s'"
    )
    time.sleep(30)
    screendump("desktop")
    status_id = run(widget % "org.nexusos.status")
    check(status_id.isdigit(), f"System Status widget present (id {status_id})")
    run(activate % status_id)
    time.sleep(25)
    screendump("desktop-status-panel")
    run(activate % status_id)
    launcher_id = run(widget % "org.nexusos.launcher")
    run(activate % launcher_id)
    time.sleep(20)
    screendump("desktop-launcher-expanded")
    run(activate % launcher_id)
    status = run(
        'nexus system desktop-status --json --no-updates | python3 -c \'import json,sys; d=json.load(sys.stdin); print(d["services"]["running"])\'',
        300,
    )
    check(
        status.isdigit() and int(status) > 10, f"desktop-status backend in the live session ({status} services running)"
    )

    # Installer storage support and the LVM layout helper, on the VM's empty virtual disk.
    tool = "sudo /usr/libexec/nexusos/nexusos-lvm-layout"
    check(
        run("command -v mkfs.xfs pvcreate mkfs.btrfs | wc -l") == "3",
        "xfsprogs, lvm2 and btrfs-progs in the live image",
    )
    check(
        run("dpkg-query -W -f '${Version}' calamares").endswith("+nexusos1"), "installer is the NexusOS Calamares build"
    )
    check(
        "refusing to erase" in run(f"{tool} --disk /dev/vda --yes 2>&1; true"),
        "LVM helper refuses without --confirm-disk",
    )
    medium = run("findmnt -n -o SOURCE /cdrom | sed 's/[0-9]*$//'")
    check(
        "live medium" in run(f"{tool} --disk {medium} --confirm-disk {medium} --yes 2>&1; true")
        or "not a" in run(f"{tool} --disk {medium} --confirm-disk {medium} --yes 2>&1; true"),
        f"LVM helper refuses the live medium ({medium})",
    )
    created = run(f"{tool} --disk /dev/vda --fs xfs --confirm-disk /dev/vda --yes >/tmp/lvm.log 2>&1; echo rc=$?", 600)
    check(created.endswith("rc=0"), "LVM layout created on the virtual disk (" + created + ")")
    if not created.endswith("rc=0"):
        print(run("tail -15 /tmp/lvm.log"))
    layout = run("lsblk -rn -o NAME,FSTYPE,LABEL /dev/vda")
    print("      " + layout.replace("\n", "\n      "), flush=True)
    for fstype, label in (("ext4", "nexus-boot"), ("LVM2_member", ""), ("swap", "nexus-swap"), ("xfs", "nexus-root")):
        check(fstype in layout and label in layout, f"layout has {fstype} {label}".strip())
    lvs = run("sudo lvs --noheadings -o lv_name,lv_size nexus | tr -s ' '")
    vfree = run("sudo vgs --noheadings --units g -o vg_free nexus | tr -d ' '")
    check("root" in lvs and "swap" in lvs, f"volume group nexus: {lvs.replace(chr(10), ',')}; free {vfree}")

    # The installer window (start only; nothing is installed)
    run("(sudo -E nexusos-install >/tmp/inst.log 2>&1 &) ; sleep 1; echo started")
    time.sleep(90)
    screendump("installer")
    check(run("pgrep -x calamares >/dev/null && echo yes") == "yes", "installer (Calamares) starts")
    calamares_log = run(
        "sudo sh -c 'cat /root/.cache/calamares/session.log 2>/dev/null' | grep -cE 'failed modules|not found in module'"
    )
    check(calamares_log == "0", "installer loads every module")

s.sendall(b"exit\r")
sys.exit(fails)
