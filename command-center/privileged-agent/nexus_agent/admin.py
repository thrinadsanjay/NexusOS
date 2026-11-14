"""``nexus-admin``: run one allow-listed operation as root, started through ``sudo``.

The Command Center (running as the logged-in user) starts::

    sudo [-n | -S -p ""] /usr/lib/nexusos/nexus-admin run

``sudo`` decides whether the user may become root (NOPASSWD rule, password,
or refused) and logs the attempt. This helper then speaks the agent protocol
over stdio: one request line on stdin, events on stdout, optional
``{"type": "cancel"}`` lines on stdin while it runs. It never runs a command
line, a shell fragment or anything outside ``ops.REGISTRY``; every request is
validated and written to the audit log with the invoking user (``SUDO_UID``).

``nexus-admin probe`` prints ``{"type": "hello", ...}`` and exits; the
Command Center uses it to learn whether sudo needs a password.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
from typing import Any

from nexus_agent import execute

MAX_REQUEST = 256 * 1024


def _caller() -> tuple[int, int]:
    try:
        uid = int(os.environ.get("SUDO_UID", "0"))
    except ValueError:
        uid = 0
    return uid, os.getppid()


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    out = sys.stdout
    lock = threading.Lock()

    def send(event: dict[str, Any]) -> None:
        with lock:
            try:
                out.write(json.dumps(event) + "\n")
                out.flush()
            except (BrokenPipeError, ValueError):
                pass

    if os.geteuid() != 0:
        send({"type": "error", "code": "unauthorized", "message": "nexus-admin must be started through sudo"})
        return 77
    if args[:1] == ["probe"]:
        send({"type": "hello", "uid": _caller()[0]})
        return 0
    if args[:1] != ["run"]:
        sys.stderr.write("usage: nexus-admin run|probe\n")
        return 64

    send({"type": "hello", "uid": _caller()[0]})  # sudo accepted the caller: the client stops waiting for a password
    uid, pid = _caller()
    raw = sys.stdin.readline(MAX_REQUEST + 1)
    if not raw or len(raw) > MAX_REQUEST:
        send({"type": "error", "code": "bad-request", "message": "empty or oversized request"})
        return 65
    try:
        name, params = execute.parse_request(json.loads(raw))
    except ValueError:
        send({"type": "error", "code": "bad-request", "message": "malformed request"})
        return 65

    cancelled = threading.Event()

    def on_signal(_signum: int, _frame: Any) -> None:  # sudo relays SIGTERM/SIGINT from the client
        cancelled.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    def watch_cancel() -> None:
        for line in sys.stdin:
            try:
                if json.loads(line).get("type") == "cancel":
                    cancelled.set()
            except ValueError:
                continue
        cancelled.set()  # the Command Center went away

    threading.Thread(target=watch_cancel, daemon=True).start()
    execute.execute(name, params, send=send, cancelled=cancelled, uid=uid, pid=pid, authorize=None, via="sudo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
