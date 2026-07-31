from __future__ import annotations

import hmac
import json
import logging
import os
import re
import socket
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger("velvet.hermes_operator_gateway")
_MAX_REQUEST_BYTES = 8 * 1024
_MAX_UPSTREAM_BYTES = 256 * 1024
_SENSITIVE_KEY = re.compile(r"(?:token|password|secret|authorization|api[_-]?key)", re.I)
_SENSITIVE_VALUE = re.compile(
    r"(?i)\b(token|password|secret|authorization|api[_-]?key)\b"
    r"(\s*[:=]\s*|\s+)([^\s,;]{6,})"
)
_BEARER_VALUE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}")


@dataclass(frozen=True, slots=True)
class Project:
    base_url: str
    token: str
    services: frozenset[str]
    restart_routes: dict[str, str]


class ConfigurationError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be configured")
    return value


def _project_config() -> dict[str, Project]:
    return {
        "velvet": Project(
            base_url=os.getenv(
                "VELVET_SUPERVISOR_BASE_URL",
                "http://supervisor-proxy:8765",
            ).rstrip("/"),
            token=_required("VELVET_SUPERVISOR_TOKEN"),
            services=frozenset({"bot"}),
            restart_routes={"bot": "/v1/restart"},
        ),
        "max": Project(
            base_url=os.getenv(
                "ROMATIC_SUPERVISOR_BASE_URL",
                "http://romatic-supervisor:8765",
            ).rstrip("/"),
            token=_required("ROMATIC_SUPERVISOR_TOKEN"),
            services=frozenset({"bot", "userbot"}),
            restart_routes={
                "bot": "/v1/restart",
                "userbot": "/v1/restart-userbot",
            },
        ),
    }


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
        raise RuntimeError("Operator upstream returned invalid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError("Operator upstream response must be a JSON object")
    return _redact(value)


class UpstreamClient:
    def __init__(self, projects: dict[str, Project]) -> None:
        self.projects = projects
        self.timeout = max(
            3,
            min(int(os.getenv("HERMES_OPS_UPSTREAM_TIMEOUT_SECONDS", "30")), 120),
        )

    def request(
        self,
        project_name: str,
        method: str,
        route: str,
    ) -> tuple[int, dict[str, Any]]:
        project = self.projects[project_name]
        request = Request(
            f"{project.base_url}{route}",
            data=b"{}" if method == "POST" else None,
            method=method,
            headers={
                "Authorization": f"Bearer {project.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Connection": "close",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(_MAX_UPSTREAM_BYTES + 1)
                status = int(response.status)
        except HTTPError as error:
            raw = error.read(_MAX_UPSTREAM_BYTES + 1)
            status = int(error.code)
        except (URLError, TimeoutError, OSError) as error:
            raise RuntimeError("Supervisor is unavailable") from error
        if len(raw) > _MAX_UPSTREAM_BYTES:
            raise RuntimeError("Supervisor response is too large")
        return status, _decode_json(raw)


class HostStartClient:
    def __init__(self) -> None:
        self.socket_path = os.getenv(
            "HERMES_OPS_HOST_SOCKET",
            "/srv/hermes-operator-control/runtime/start.sock",
        ).strip()
        if not self.socket_path.startswith("/"):
            raise ConfigurationError("HERMES_OPS_HOST_SOCKET must be absolute")
        self.token = _required("HERMES_OPS_HOST_TOKEN")
        if len(self.token) < 24:
            raise ConfigurationError(
                "HERMES_OPS_HOST_TOKEN must contain at least 24 characters"
            )
        command_timeout = max(
            30,
            min(int(os.getenv("HERMES_OPS_START_TIMEOUT_SECONDS", "300")), 1800),
        )
        health_attempts = max(
            1,
            min(int(os.getenv("HERMES_OPS_START_HEALTH_ATTEMPTS", "60")), 180),
        )
        health_interval = max(
            1,
            min(int(os.getenv("HERMES_OPS_START_HEALTH_INTERVAL", "2")), 30),
        )
        self.timeout = min(
            command_timeout + health_attempts * health_interval + 30,
            2400,
        )

    def start(self, project: str, service: str) -> tuple[int, dict[str, Any]]:
        request = json.dumps(
            {"token": self.token, "project": project, "service": service},
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
                        raise RuntimeError("Host start response is too large")
                    if b"\n" in chunk:
                        break
        except (OSError, TimeoutError) as error:
            raise RuntimeError("Host start bridge is unavailable") from error
        raw = b"".join(chunks).split(b"\n", 1)[0]
        payload = _decode_json(raw)
        status = HTTPStatus.OK if payload.get("ok") is True else HTTPStatus.BAD_GATEWAY
        return status, payload


class GatewayHandler(BaseHTTPRequestHandler):
    server: "GatewayServer"

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("Hermes operator gateway - %s", format % args)

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

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health" and method == "GET":
            self._send(HTTPStatus.OK, {"ok": True, "runtime": "hermes-operator"})
            return
        if not self._require_auth():
            return
        if method == "POST" and not self._read_empty_json():
            self._send(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": "Only an empty JSON object is accepted",
                    "error_code": "invalid_request",
                },
            )
            return

        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 3 or parts[0] != "v1":
            self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        project_name = parts[1]
        action = parts[2]
        project = self.server.client.projects.get(project_name)
        if project is None:
            self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "unknown project"})
            return

        try:
            if method == "GET" and action == "status" and len(parts) == 3:
                upstream_status, result = self.server.client.request(
                    project_name,
                    "GET",
                    "/v1/status",
                )
            elif method == "GET" and action == "logs" and len(parts) == 3:
                raw_lines = parse_qs(parsed.query).get("lines", ["200"])[0]
                try:
                    lines = max(1, min(int(raw_lines), 500))
                except ValueError:
                    lines = 200
                route = (
                    f"/v1/logs?lines={lines}"
                    if project_name == "velvet"
                    else "/v1/logs"
                )
                upstream_status, result = self.server.client.request(
                    project_name,
                    "GET",
                    route,
                )
            elif method == "POST" and action == "start" and len(parts) == 4:
                service = parts[3]
                if service not in project.services:
                    raise KeyError(service)
                upstream_status, result = self.server.host_start.start(
                    project_name,
                    service,
                )
            elif method == "POST" and action == "restart" and len(parts) == 4:
                service = parts[3]
                if service not in project.services:
                    raise KeyError(service)
                upstream_status, result = self.server.client.request(
                    project_name,
                    "POST",
                    project.restart_routes[service],
                )
            elif (
                method == "POST"
                and action in {"update", "rollback"}
                and len(parts) == 3
            ):
                upstream_status, result = self.server.client.request(
                    project_name,
                    "POST",
                    f"/v1/{action}",
                )
            else:
                self._send(
                    HTTPStatus.NOT_FOUND,
                    {"ok": False, "error": "unsupported action"},
                )
                return
        except KeyError:
            self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "unknown service"})
            return
        except RuntimeError as error:
            logger.warning(
                "Hermes operator request failed project=%s action=%s: %s",
                project_name,
                action,
                error,
            )
            self._send(
                HTTPStatus.BAD_GATEWAY,
                {
                    "ok": False,
                    "error": "Operator upstream request failed",
                    "error_code": "upstream_unavailable",
                },
            )
            return

        self._send(
            upstream_status,
            {
                "ok": upstream_status < 400,
                "project": project_name,
                "action": action,
                "upstream_status": upstream_status,
                "result": result,
            },
        )

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int]) -> None:
        self.client_token = _required("HERMES_OPS_CLIENT_TOKEN")
        if len(self.client_token) < 24:
            raise ConfigurationError(
                "HERMES_OPS_CLIENT_TOKEN must contain at least 24 characters"
            )
        self.client = UpstreamClient(_project_config())
        self.host_start = HostStartClient()
        super().__init__(address, GatewayHandler)


def main() -> None:
    host = os.getenv("HERMES_OPS_GATEWAY_HOST", "0.0.0.0")
    port = int(os.getenv("HERMES_OPS_GATEWAY_PORT", "8877"))
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    server = GatewayServer((host, port))
    logger.info("Hermes operator gateway listening on %s:%s", host, port)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
