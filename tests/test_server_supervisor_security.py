from __future__ import annotations

import os
import socket
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.server_supervisor import (
    ServerSupervisorRuntime,
    ThreadingUnixHTTPServer,
    prepare_socket_path,
    secure_socket_path,
)


def _runtime_environment(directory: str) -> dict[str, str]:
    gid = os.getgid() if os.getgid() > 0 else 1
    uid = os.getuid() if os.getuid() > 0 else 1
    return {
        "VELVET_APP_DIR": directory,
        "VELVET_DATA_DIR": directory,
        "SUPERVISOR_TOKEN": "supervisor_test_token_12345678901234567890",
        "SERVER_SUPERVISOR_SOCKET_HOST": (
            f"{directory}/control/supervisor/velvet-server-supervisor.sock"
        ),
        "SERVER_SUPERVISOR_CLIENT_UID": str(uid),
        "SERVER_SUPERVISOR_CLIENT_GID": str(gid),
        "SERVER_SUPERVISOR_SOCKET_MODE": "0660",
        "SERVER_SUPERVISOR_AUTH_FAILURE_LIMIT": "2",
        "SERVER_SUPERVISOR_AUTH_FAILURE_WINDOW_SECONDS": "60",
        "SERVER_SUPERVISOR_AUTH_FAILURE_COOLDOWN_SECONDS": "30",
    }


class ServerSupervisorSecurityTests(unittest.TestCase):
    def test_peer_allowlist_requires_exact_uid_gid_or_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, _runtime_environment(directory), clear=False
        ):
            runtime = ServerSupervisorRuntime()
        expected = (runtime.socket_client_uid, runtime.socket_client_gid)
        self.assertTrue(runtime.peer_allowed(expected))
        self.assertTrue(runtime.peer_allowed((0, 0)))
        self.assertFalse(runtime.peer_allowed((expected[0] + 1, expected[1])))
        self.assertFalse(runtime.peer_allowed((expected[0], expected[1] + 1)))

    def test_repeated_auth_failures_enter_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, _runtime_environment(directory), clear=False
        ):
            runtime = ServerSupervisorRuntime()
        peer = (runtime.socket_client_uid, runtime.socket_client_gid)
        self.assertEqual(0, runtime.record_auth_failure(peer))
        self.assertEqual(30, runtime.record_auth_failure(peer))
        self.assertTrue(runtime.auth_blocked(peer))
        runtime.reset_auth_failures(peer)
        self.assertFalse(runtime.auth_blocked(peer))

    def test_regular_file_is_not_replaced_as_stale_socket(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, _runtime_environment(directory), clear=False
        ):
            runtime = ServerSupervisorRuntime()
            runtime.socket_path.parent.mkdir(parents=True)
            runtime.socket_path.write_text("not a socket", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Refusing to replace stale"):
                prepare_socket_path(runtime)
            self.assertTrue(runtime.socket_path.is_file())

    @unittest.skipUnless(hasattr(socket, "SO_PEERCRED"), "Linux SO_PEERCRED required")
    def test_socket_is_0660_and_health_requires_allowed_peer(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, _runtime_environment(directory), clear=False
        ):
            runtime = ServerSupervisorRuntime()
            prepare_socket_path(runtime)
            server = ThreadingUnixHTTPServer(str(runtime.socket_path), runtime)
            secure_socket_path(runtime)
            value = runtime.socket_path.lstat()
            self.assertEqual(0o660, stat.S_IMODE(value.st_mode))
            self.assertEqual(runtime.socket_client_gid, value.st_gid)
            thread = threading.Thread(
                target=server.serve_forever,
                kwargs={"poll_interval": 0.01},
                daemon=True,
            )
            thread.start()
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(2)
                    client.connect(str(runtime.socket_path))
                    client.sendall(
                        b"GET /health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
                    )
                    response = client.recv(4096)
                self.assertIn(b"200 OK", response)
                self.assertIn(b'"ok": true', response)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                runtime.socket_path.unlink(missing_ok=True)

    @unittest.skipUnless(hasattr(socket, "SO_PEERCRED"), "Linux SO_PEERCRED required")
    def test_protected_endpoint_still_requires_bearer_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, _runtime_environment(directory), clear=False
        ):
            runtime = ServerSupervisorRuntime()
            prepare_socket_path(runtime)
            server = ThreadingUnixHTTPServer(str(runtime.socket_path), runtime)
            secure_socket_path(runtime)
            thread = threading.Thread(
                target=server.serve_forever,
                kwargs={"poll_interval": 0.01},
                daemon=True,
            )
            thread.start()
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(2)
                    client.connect(str(runtime.socket_path))
                    client.sendall(
                        b"GET /v1/console HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
                    )
                    response = client.recv(4096)
                self.assertIn(b"401 Unauthorized", response)
                self.assertIn(b"invalid_token", response)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                runtime.socket_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
