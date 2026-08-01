from __future__ import annotations

import hmac
import json
import os
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

_ALLOWED_VIEWS = frozenset(
    {"summary", "resources", "containers", "services", "gpu", "models", "processes", "incidents"}
)
_MAX_RESPONSE_BYTES = 512 * 1024


class ConfigurationError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be configured")
    return value


class HostMonitorClient:
    def __init__(self) -> None:
        self.socket_path = _required("HERMES_OPS_MONITOR_SOCKET")
        self.host_token = _required("HERMES_OPS_MONITOR_TOKEN")
        self.timeout = max(2, min(int(os.getenv("HERMES_OPS_MONITOR_REQUEST_TIMEOUT_SECONDS", "20")), 40))

    def collect(self, view: str) -> dict[str, Any]:
        request = json.dumps({"token": self.host_token, "view": view}).encode("utf-8") + b"\n"
        chunks: list[bytes] = []
        size = 0
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.timeout)
            connection.connect(self.socket_path)
            connection.sendall(request)
            while True:
                chunk = connection.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > _MAX_RESPONSE_BYTES:
                    raise RuntimeError("Hermes monitor host response is too large")
                if b"\n" in chunk:
                    break
        raw = b"".join(chunks).split(b"\n", 1)[0]
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Hermes monitor host response must be an object")
        return payload


class MonitorGateway:
    def __init__(self) -> None:
        self.client_token = _required("HERMES_OPS_CLIENT_TOKEN")
        self.host = os.getenv("HERMES_MONITOR_GATEWAY_HOST", "0.0.0.0")
        self.port = int(os.getenv("HERMES_MONITOR_GATEWAY_PORT", "8879"))
        self.host_client = HostMonitorClient()


class RequestHandler(BaseHTTPRequestHandler):
    server: "MonitorHTTPServer"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok"})
            return
        prefix = "/v1/monitor/"
        if not self.path.startswith(prefix) or "?" in self.path or "#" in self.path:
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
            return
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Unauthorized"})
            return
        view = self.path[len(prefix) :]
        if view not in _ALLOWED_VIEWS or "/" in view:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Unknown monitor view"})
            return
        try:
            payload = self.server.gateway.host_client.collect(view)
        except Exception:
            self._json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "error": "Hermes monitor host bridge is unavailable"},
            )
            return
        status = HTTPStatus.OK if payload.get("ok") is True else HTTPStatus.BAD_GATEWAY
        self._json(status, payload)

    def do_POST(self) -> None:  # noqa: N802
        self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "Read-only gateway"})

    def do_PUT(self) -> None:  # noqa: N802
        self.do_POST()

    def do_DELETE(self) -> None:  # noqa: N802
        self.do_POST()

    def log_message(self, format: str, *args: object) -> None:
        return

    def _authorized(self) -> bool:
        value = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.gateway.client_token}"
        return hmac.compare_digest(value, expected)

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class MonitorHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], gateway: MonitorGateway) -> None:
        self.gateway = gateway
        super().__init__(address, RequestHandler)


def main() -> None:
    gateway = MonitorGateway()
    server = MonitorHTTPServer((gateway.host, gateway.port), gateway)
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
