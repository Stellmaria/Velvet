from __future__ import annotations

import hmac
import json
import logging
import os
import re
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


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[redacted]" if _SENSITIVE_KEY.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _decode_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Supervisor returned an invalid JSON response") from error
    if not isinstance(value, dict):
        raise RuntimeError("Supervisor response must be a JSON object")
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

    def start(self, project_name: str, service: str) -> tuple[int, dict[str, Any]]:
        status_code, status_payload = self.request(
            project_name,
            "GET",
            "/v1/status",
        )
        if status_code >= 400:
            return status_code, status_payload

        if project_name == "velvet":
            service_state = (
                status_payload.get("status", {}).get("bot", {})
                if isinstance(status_payload.get("status"), dict)
                else {}
            )
        else:
            service_state = status_payload.get(service, {})
        if not isinstance(service_state, dict):
            service_state = {}

        if service_state.get("error"):
            return HTTPStatus.BAD_GATEWAY, {
                "ok": False,
                "error": f"Cannot determine {project_name}/{service} state",
                "error_code": "status_probe_failed",
            }

        if service_state.get("running") is True:
            return HTTPStatus.OK, {
                "ok": True,
                "message": f"{project_name}/{service} is already running",
                "status": status_payload,
            }

        status_name = service_state.get("status")
        if status_name == "missing" or (
            status_name is None and service_state.get("pid") is None
        ):
            return self.request(project_name, "POST", "/v1/update")

        route = self.projects[project_name].restart_routes[service]
        return self.request(project_name, "POST", route)


class GatewayHandler(BaseHTTPRequestHandler):
    server: "GatewayServer"

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("Hermes operator gateway - %s", format % args)

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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
                route = f"/v1/logs?lines={lines}" if project_name == "velvet" else "/v1/logs"
                upstream_status, result = self.server.client.request(
                    project_name,
                    "GET",
                    route,
                )
            elif method == "POST" and action == "start" and len(parts) == 4:
                service = parts[3]
                if service not in project.services:
                    raise KeyError(service)
                upstream_status, result = self.server.client.start(project_name, service)
            elif method == "POST" and action == "restart" and len(parts) == 4:
                service = parts[3]
                if service not in project.services:
                    raise KeyError(service)
                upstream_status, result = self.server.client.request(
                    project_name,
                    "POST",
                    project.restart_routes[service],
                )
            elif method == "POST" and action in {"update", "rollback"} and len(parts) == 3:
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
                    "error": "Supervisor request failed",
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
            raise ConfigurationError("HERMES_OPS_CLIENT_TOKEN must contain at least 24 characters")
        self.client = UpstreamClient(_project_config())
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
