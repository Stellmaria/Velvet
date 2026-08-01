from __future__ import annotations

import hmac
import json
import logging
import os
import re
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("velvet.hermes_reconcile_gateway")
_MAX_REQUEST_BYTES = 8 * 1024
_MAX_UPSTREAM_BYTES = 256 * 1024
_TARGETS = frozenset({"coders", "entities", "librarian", "all"})
_TASK_ID = re.compile(r"^reconcile_[0-9a-f]{32}$")
_SENSITIVE_KEY = re.compile(r"(?:token|password|secret|authorization|api[_-]?key)", re.I)
_SENSITIVE_VALUE = re.compile(
    r"(?i)\b(token|password|secret|authorization|api[_-]?key)\b"
    r"(\s*[:=]\s*|\s+)([^\s,;]{6,})"
)
_BEARER_VALUE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}")


class ConfigurationError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be configured")
    return value


def _scrub_string(value: str) -> str:
    value = _BEARER_VALUE.sub("Bearer [redacted]", value)
    return _SENSITIVE_VALUE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[redacted]",
        value,
    )


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[redacted]" if _SENSITIVE_KEY.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _scrub_string(value)
    return value


def _decode_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Reconcile bridge returned invalid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError("Reconcile bridge response must be a JSON object")
    return _redact(value)


class HostReconcileClient:
    def __init__(self) -> None:
        self.socket_path = os.getenv(
            "HERMES_OPS_RECONCILE_SOCKET",
            "/run/hermes-operator-reconcile/reconcile.sock",
        ).strip()
        if not self.socket_path.startswith("/"):
            raise ConfigurationError("HERMES_OPS_RECONCILE_SOCKET must be absolute")
        self.token = _required("HERMES_OPS_RECONCILE_TOKEN")
        if len(self.token) < 24:
            raise ConfigurationError(
                "HERMES_OPS_RECONCILE_TOKEN must contain at least 24 characters"
            )
        self.timeout = max(
            5,
            min(int(os.getenv("HERMES_OPS_RECONCILE_REQUEST_TIMEOUT_SECONDS", "30")), 120),
        )

    def request(self, payload: dict[str, str]) -> tuple[int, dict[str, Any]]:
        body = {"token": self.token, **payload}
        request = json.dumps(
            body,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        chunks: list[bytes] = []
        received = 0
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout)
                connection.connect(self.socket_path)
                connection.sendall(request)
                while True:
                    chunk = connection.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    received += len(chunk)
                    if received > _MAX_UPSTREAM_BYTES:
                        raise RuntimeError("Reconcile bridge response is too large")
                    if b"\n" in chunk:
                        break
        except (OSError, TimeoutError) as error:
            raise RuntimeError("Reconcile bridge is unavailable") from error
        raw = b"".join(chunks).split(b"\n", 1)[0]
        result = _decode_json(raw)
        status = HTTPStatus.OK if result.get("ok") is True else HTTPStatus.BAD_GATEWAY
        return status, result


class GatewayHandler(BaseHTTPRequestHandler):
    server: "GatewayServer"

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("Hermes reconcile gateway - %s", format % args)

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(_redact(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        expected = f"Bearer {self.server.client_token}"
        provided = self.headers.get("Authorization", "")
        return hmac.compare_digest(provided, expected)

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self._send(
            HTTPStatus.UNAUTHORIZED,
            {"ok": False, "error": "unauthorized", "error_code": "unauthorized"},
        )
        return False

    def _read_empty_json(self) -> bool:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return False
        if length < 0 or length > _MAX_REQUEST_BYTES:
            return False
        if not length:
            return True
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return value == {}

    def _bridge(self, payload: dict[str, str]) -> None:
        try:
            status, result = self.server.host_reconcile.request(payload)
        except RuntimeError as error:
            logger.warning("Hermes reconcile gateway request failed: %s", error)
            self._send(
                HTTPStatus.BAD_GATEWAY,
                {
                    "ok": False,
                    "error": "Reconcile bridge request failed",
                    "error_code": "upstream_unavailable",
                },
            )
            return
        self._send(status, result)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(HTTPStatus.OK, {"ok": True, "runtime": "hermes-reconcile"})
            return
        if not self._require_auth():
            return
        parts = [part for part in parsed.path.split("/") if part]
        if parts == ["v1", "tasks"]:
            self._bridge({"action": "list"})
            return
        if len(parts) == 3 and parts[:2] == ["v1", "tasks"] and _TASK_ID.fullmatch(parts[2]):
            self._bridge({"action": "status", "task_id": parts[2]})
            return
        self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_auth():
            return
        if not self._read_empty_json():
            self._send(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": "Only an empty JSON object is accepted",
                    "error_code": "invalid_request",
                },
            )
            return
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 3 or parts[:2] != ["v1", "reconcile"]:
            self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        target = parts[2]
        if target not in _TARGETS:
            self._send(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": "unknown target", "error_code": "unknown_target"},
            )
            return
        self._bridge({"action": "submit", "target": target})


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int]) -> None:
        self.client_token = _required("HERMES_OPS_CLIENT_TOKEN")
        if len(self.client_token) < 24:
            raise ConfigurationError(
                "HERMES_OPS_CLIENT_TOKEN must contain at least 24 characters"
            )
        self.host_reconcile = HostReconcileClient()
        super().__init__(address, GatewayHandler)


def main() -> None:
    host = os.getenv("HERMES_RECONCILE_GATEWAY_HOST", "0.0.0.0")
    port = int(os.getenv("HERMES_RECONCILE_GATEWAY_PORT", "8878"))
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    server = GatewayServer((host, port))
    logger.info("Hermes reconcile gateway listening on %s:%s", host, port)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
