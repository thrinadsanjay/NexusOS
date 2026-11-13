"""Socket server: systemd socket activation, per-connection threads, idle exit."""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import socket
import threading
import time
from typing import Any

from nexus_core.errors import NexusError, ValidationError
from pydantic import ValidationError as PydanticValidationError

from nexus_agent import audit, ops
from nexus_agent.auth import Authorizer, peer_of

log = logging.getLogger("nexus.agent")
SD_LISTEN_FDS_START = 3
MAX_REQUEST = 256 * 1024


class Agent:
    def __init__(self, sock: socket.socket, idle_timeout: float, authorizer: Authorizer | None = None) -> None:
        self.sock = sock
        self.idle_timeout = idle_timeout
        self.authorizer = authorizer or Authorizer()
        self.active = 0
        self.last_activity = time.monotonic()
        self.lock = threading.Lock()
        self.stopping = threading.Event()

    # ------------------------------------------------------------ lifecycle
    def serve(self) -> None:
        self.sock.settimeout(1.0)
        while not self.stopping.is_set():
            try:
                conn, _ = self.sock.accept()
            except TimeoutError:
                if self._idle():
                    log.info("idle for %ss, exiting (socket activation restarts on demand)", self.idle_timeout)
                    return
                continue
            with self.lock:
                self.active += 1
                self.last_activity = time.monotonic()
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _idle(self) -> bool:
        with self.lock:
            return (
                self.idle_timeout > 0
                and self.active == 0
                and (time.monotonic() - self.last_activity > self.idle_timeout)
            )

    # ------------------------------------------------------------ connection
    def _handle(self, conn: socket.socket) -> None:
        writer_lock = threading.Lock()

        def send(event: dict[str, Any]) -> None:
            with writer_lock, contextlib.suppress(OSError):
                conn.sendall((json.dumps(event) + "\n").encode())

        try:
            peer = peer_of(conn)
            reader = conn.makefile("rb")
            raw = reader.readline(MAX_REQUEST + 1)
            if not raw or len(raw) > MAX_REQUEST:
                send({"type": "error", "code": "bad-request", "message": "empty or oversized request"})
                return
            try:
                request = json.loads(raw)
                name = request["op"]
                params = request.get("params") or {}
                if request.get("v") != 1 or not isinstance(params, dict):
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                send({"type": "error", "code": "bad-request", "message": "malformed request"})
                return
            operation = ops.REGISTRY.get(name)
            if operation is None:
                audit.record(peer.uid, peer.pid, str(name)[:64], {}, "rejected", "unknown op")
                send({"type": "error", "code": "unknown-op", "message": f"unsupported operation {name!r}"})
                return
            try:
                parsed = operation.model(**params)
            except (PydanticValidationError, TypeError, NexusError) as exc:
                message = exc.message if isinstance(exc, NexusError) else str(exc)
                audit.record(peer.uid, peer.pid, name, params, "rejected", "invalid parameters")
                send({"type": "error", "code": "invalid", "message": f"invalid parameters: {message}"[:500]})
                return
            if operation.action:
                allowed, how = self.authorizer.authorize(peer, operation.action)
                if not allowed:
                    audit.record(peer.uid, peer.pid, name, params, "denied", how)
                    send({"type": "error", "code": "unauthorized", "message": f"not authorized: {how}"})
                    return
            cancelled = threading.Event()

            def watch_cancel() -> None:
                for line in reader:
                    try:
                        if json.loads(line).get("type") == "cancel":
                            cancelled.set()
                    except ValueError:
                        continue
                cancelled.set()  # client went away: treat as cancel request

            threading.Thread(target=watch_cancel, daemon=True).start()
            ctx = ops.Context(emit=send, cancelled=cancelled, uid=peer.uid)
            try:
                data = operation.handler(parsed, ctx)
                audit.record(peer.uid, peer.pid, name, params, "ok")
                send({"type": "result", "ok": True, "data": data})
            except NexusError as exc:
                code = "invalid" if isinstance(exc, ValidationError) else getattr(exc, "code", "failed")
                message = exc.message + (f" ({exc.hint})" if exc.hint else "")
                audit.record(peer.uid, peer.pid, name, params, "failed", message)
                send({"type": "error", "code": code if isinstance(code, str) else "failed", "message": message})
            except (ValueError, OSError) as exc:
                audit.record(peer.uid, peer.pid, name, params, "failed", str(exc))
                send({"type": "error", "code": "failed", "message": f"{exc.__class__.__name__}: {exc}"[:500]})
        except Exception:  # never leave a client waiting without an answer
            log.exception("internal error")
            send({"type": "error", "code": "internal", "message": "internal agent error (see journal)"})
        finally:
            conn.close()
            with self.lock:
                self.active -= 1
                self.last_activity = time.monotonic()


def _systemd_socket() -> socket.socket | None:
    if os.environ.get("LISTEN_PID") == str(os.getpid()) and int(os.environ.get("LISTEN_FDS", "0")) >= 1:
        return socket.socket(fileno=SD_LISTEN_FDS_START)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nexusos-agent", description="NexusOS management agent")
    parser.add_argument("--socket", help="listen on this path instead of a systemd-provided socket (development)")
    parser.add_argument("--socket-mode", default="660", help="permissions for --socket (octal)")
    parser.add_argument("--idle-timeout", type=float, default=120.0, help="exit after N idle seconds (0: never)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    sock = _systemd_socket()
    if sock is None:
        if not args.socket:
            parser.error("no systemd socket passed; use --socket PATH for development")
        if os.path.exists(args.socket):
            os.unlink(args.socket)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        mode = int(args.socket_mode, 8)
        previous = os.umask(0o777 & ~mode)  # create the socket with its final mode: no permissive window
        try:
            sock.bind(args.socket)
        finally:
            os.umask(previous)
        os.chmod(args.socket, mode)
        sock.listen(16)
    try:
        Agent(sock, args.idle_timeout).serve()
    finally:
        if args.socket and os.path.exists(args.socket):
            os.unlink(args.socket)
    return 0
