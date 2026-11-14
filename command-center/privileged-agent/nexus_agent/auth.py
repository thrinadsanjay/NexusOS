"""Caller identification (SO_PEERCRED) and polkit authorization."""

from __future__ import annotations

import os
import shutil
import socket
import struct
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Peer:
    pid: int
    uid: int
    gid: int

    @property
    def start_time(self) -> str | None:
        """Process start time (field 22 of /proc/<pid>/stat) to make polkit subject checks race-free."""
        try:
            stat = open(f"/proc/{self.pid}/stat", encoding="utf-8").read()  # noqa: SIM115
        except OSError:
            return None
        fields = stat.rsplit(")", 1)[1].split()
        return fields[19] if len(fields) > 19 else None


def peer_of(conn: socket.socket) -> Peer:
    creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    pid, uid, gid = struct.unpack("3i", creds)
    return Peer(pid, uid, gid)


class Authorizer:
    """Root callers are trusted; everyone else must pass ``pkcheck`` for the operation's action id.

    If polkit is unavailable the agent fails closed (denies).
    """

    def __init__(self, pkcheck: str | None = None) -> None:
        self.pkcheck = pkcheck or shutil.which("pkcheck") or "/usr/bin/pkcheck"

    def authorize(self, peer: Peer, action_id: str) -> tuple[bool, str]:
        if peer.uid == 0:
            return True, "root"
        if not os.path.exists(self.pkcheck):
            return False, "polkit (pkcheck) not available"
        start = peer.start_time
        subject = f"{peer.pid},{start},{peer.uid}" if start else f"{peer.pid}"
        try:
            proc = subprocess.run(  # noqa: S603 — pkcheck path resolved at start; action id from the op table, subject from SO_PEERCRED
                [self.pkcheck, "--action-id", action_id, "--process", subject, "--allow-user-interaction"],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"polkit check failed: {exc.__class__.__name__}"
        if proc.returncode == 0:
            return True, "polkit"
        return False, (proc.stderr.strip() or "not authorized")[:200]
