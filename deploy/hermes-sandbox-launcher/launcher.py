#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import socket
import struct
import threading
from typing import Any

from launcher_contract import (
    NETWORK,
    UID,
    LauncherProtocolError,
    _LISTEN_FDS_START,
    _MAX_REQUEST_BYTES,
    audit,
    exact_fields,
    validate_run,
)
from launcher_runtime import Launcher

_MAX_CONNECTIONS = 8
_ALLOWED_PEER_UIDS = frozenset({0, UID})


def receive_json(connection: socket.socket) -> dict[str, Any]:
    chunks: list[bytes] = []
    total = 0
    found_newline = False
    while not found_newline:
        chunk = connection.recv(65_536)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > _MAX_REQUEST_BYTES:
            raise LauncherProtocolError("request exceeds 128 KiB")
        found_newline = b"\n" in chunk
    raw = b"".join(chunks).split(b"\n", 1)[0]
    if not raw:
        raise LauncherProtocolError("empty launcher request")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LauncherProtocolError("invalid JSON request") from error
    if not isinstance(payload, dict):
        raise LauncherProtocolError("request must be a JSON object")
    return payload


def send_json(connection: socket.socket, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    ) + b"\n"
    connection.sendall(body)


def peer_identity(connection: socket.socket) -> tuple[int, int, int]:
    credentials = connection.getsockopt(
        socket.SOL_SOCKET,
        socket.SO_PEERCRED,
        struct.calcsize("3i"),
    )
    pid, uid, gid = struct.unpack("3i", credentials)
    if uid not in _ALLOWED_PEER_UIDS:
        raise LauncherProtocolError("launcher peer UID is not allowlisted")
    return pid, uid, gid


def handle_connection(connection: socket.socket, launcher: Launcher) -> None:
    peer_pid = 0
    peer_uid = -1
    try:
        peer_pid, peer_uid, _peer_gid = peer_identity(connection)
        payload = receive_json(connection)
        action = payload.get("action")
        if action == "ping":
            exact_fields(payload, {"action"})
            send_json(
                connection,
                {
                    "ok": True,
                    "backend": "host-docker-launcher",
                    "nested_bwrap": False,
                    "network": NETWORK,
                },
            )
        elif action == "probe":
            exact_fields(payload, {"action", "project"})
            project = payload.get("project")
            if not isinstance(project, str):
                raise LauncherProtocolError("invalid project")
            send_json(connection, {"ok": True, "result": launcher.probe(project)})
        elif action == "cancel":
            exact_fields(payload, {"action", "run_id"})
            run_id = payload.get("run_id")
            if not isinstance(run_id, str):
                raise LauncherProtocolError("invalid run_id")
            send_json(connection, {"ok": True, "cancelled": launcher.cancel(run_id)})
        elif action == "run":
            request = validate_run(payload)
            send_json(connection, {"ok": True, "result": launcher.run(request)})
        else:
            raise LauncherProtocolError("unsupported action")
    except LauncherProtocolError as error:
        send_json(connection, {"ok": False, "error": str(error)})
        audit(
            "request_rejected",
            peer_pid=peer_pid,
            peer_uid=peer_uid,
            error=str(error),
        )
    except Exception as error:
        audit(
            "internal_error",
            peer_pid=peer_pid,
            peer_uid=peer_uid,
            error_type=type(error).__name__,
        )
        try:
            send_json(connection, {"ok": False, "error": "launcher internal error"})
        except OSError:
            pass
    finally:
        connection.close()


def inherited_listener() -> socket.socket:
    listen_pid = int(os.environ.get("LISTEN_PID", "0") or 0)
    listen_fds = int(os.environ.get("LISTEN_FDS", "0") or 0)
    if listen_pid != os.getpid() or listen_fds != 1:
        raise RuntimeError("launcher requires exactly one systemd socket")
    listener = socket.fromfd(
        _LISTEN_FDS_START,
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )
    listener.setblocking(True)
    return listener


def main() -> int:
    launcher = Launcher()
    launcher.cleanup_stale()
    listener = inherited_listener()
    stopping = threading.Event()
    slots = threading.BoundedSemaphore(_MAX_CONNECTIONS)

    def stop_handler(_signum: int, _frame: Any) -> None:
        stopping.set()
        try:
            listener.close()
        except OSError:
            pass

    def worker(connection: socket.socket) -> None:
        try:
            handle_connection(connection, launcher)
        finally:
            slots.release()

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    audit("launcher_ready", network=NETWORK, max_connections=_MAX_CONNECTIONS)
    try:
        while not stopping.is_set():
            try:
                connection, _ = listener.accept()
            except OSError:
                if stopping.is_set():
                    break
                raise
            if not slots.acquire(blocking=False):
                try:
                    send_json(
                        connection,
                        {"ok": False, "error": "launcher capacity exhausted"},
                    )
                finally:
                    connection.close()
                continue
            threading.Thread(
                target=worker,
                args=(connection,),
                daemon=True,
                name="hermes-sandbox-request",
            ).start()
    finally:
        launcher.shutdown()
        audit("launcher_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
