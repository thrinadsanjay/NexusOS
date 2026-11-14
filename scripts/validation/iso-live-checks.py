#!/usr/bin/env python3
"""Log in to a booted NexusOS live image on its serial console and check the session.

Used by iso-boot-smoke.sh inside the test container. Connects to QEMU's serial socket,
logs in as the passwordless live account and runs read-only checks. Prints PASS/FAIL lines
and writes the raw console transcript to OUT/live-console.log.

usage: iso-live-checks.py SERIAL_SOCKET OUT_DIR MINUTES
"""

from __future__ import annotations

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
s.sendall(b"exit\r")
sys.exit(fails)
