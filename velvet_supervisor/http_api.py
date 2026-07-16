from __future__ import annotations

import hmac
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .runtime import OperationConflict, VelvetSupervisor

logger = logging.getLogger(__name__)

_MAX_BODY_BYTES = 128 * 1024


class SupervisorHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        runtime: VelvetSupervisor,
    ) -> None:
        self.runtime = runtime
        super().__init__(server_address, SupervisorRequestHandler)


class SupervisorRequestHandler(BaseHTTPRequestHandler):
    server: SupervisorHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("Supervisor API %s - %s", self.address_string(), format % args)

    def _authorized(self) -> bool:
        expected = f"Bearer {self.server.runtime.settings.api_token}"
        provided = self.headers.get("Authorization", "")
        return hmac.compare_digest(provided, expected)

    def _send(
        self,
        status: HTTPStatus,
        payload: dict[str, Any],
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self._send(
            HTTPStatus.UNAUTHORIZED,
            {"ok": False, "error": "Неверный токен Supervisor."},
        )
        return False

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ValueError("Некорректный Content-Length.") from error
        if length < 0 or length > _MAX_BODY_BYTES:
            raise ValueError("Тело запроса слишком большое.")
        if not length:
            return {}
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON-запрос должен быть объектом.")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(HTTPStatus.OK, {"ok": True})
            return
        if not self._require_auth():
            return
        try:
            if parsed.path == "/v1/status":
                self._send(
                    HTTPStatus.OK,
                    {"ok": True, "status": self.server.runtime.status()},
                )
                return
            if parsed.path == "/v1/logs":
                query = parse_qs(parsed.query)
                raw_lines = query.get("lines", ["200"])[0]
                try:
                    lines = int(raw_lines)
                except ValueError:
                    lines = 200
                self._send(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "lines": self.server.runtime.log_tail(lines),
                    },
                )
                return
            if parsed.path == "/v1/codex":
                query = parse_qs(parsed.query)
                raw_limit = query.get("limit", ["20"])[0]
                try:
                    limit = int(raw_limit)
                except ValueError:
                    limit = 20
                limit = max(1, min(limit, 100))
                self._send(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "tasks": self.server.runtime.codex.list_tasks(limit=limit),
                    },
                )
                return
            prefix = "/v1/codex/"
            if parsed.path.startswith(prefix):
                task_id = parsed.path[len(prefix) :].strip("/")
                task = self.server.runtime.codex.get_dict(task_id)
                if task is None:
                    self._send(
                        HTTPStatus.NOT_FOUND,
                        {"ok": False, "error": "Задача Codex не найдена."},
                    )
                else:
                    self._send(HTTPStatus.OK, {"ok": True, "task": task})
                return
            self._send(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": "Маршрут не найден."},
            )
        except Exception as error:
            logger.exception("Supervisor GET failed path=%s", parsed.path)
            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": str(error)},
            )

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/v1/restart":
                operation = self.server.runtime.schedule_restart()
                self._accepted(operation.to_dict())
                return
            if parsed.path == "/v1/update":
                operation = self.server.runtime.schedule_update()
                self._accepted(operation.to_dict())
                return
            if parsed.path == "/v1/rollback":
                target = payload.get("target_sha")
                operation = self.server.runtime.schedule_rollback(
                    str(target).strip() if target else None
                )
                self._accepted(operation.to_dict())
                return
            if parsed.path == "/v1/codex":
                prompt = str(payload.get("prompt", ""))
                requested_by = str(payload.get("requested_by", "telegram"))
                task = self.server.runtime.codex.create(prompt, requested_by)
                self._send(
                    HTTPStatus.ACCEPTED,
                    {"ok": True, "task": task.to_dict()},
                )
                return

            prefix = "/v1/codex/"
            if parsed.path.startswith(prefix):
                suffix = parsed.path[len(prefix) :].strip("/")
                parts = suffix.split("/")
                if len(parts) != 2:
                    raise ValueError("Некорректный маршрут задачи Codex.")
                task_id, action = parts
                if action == "apply":
                    operation = self.server.runtime.schedule_codex_apply(task_id)
                    self._accepted(operation.to_dict())
                    return
                if action == "reject":
                    task = self.server.runtime.reject_codex_task(task_id)
                    self._send(HTTPStatus.OK, {"ok": True, "task": task})
                    return
                if action == "push":
                    operation = self.server.runtime.schedule_codex_push(task_id)
                    self._accepted(operation.to_dict())
                    return
                raise ValueError("Неизвестное действие задачи Codex.")

            self._send(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": "Маршрут не найден."},
            )
        except OperationConflict as error:
            self._send(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": str(error)},
            )
        except (ValueError, RuntimeError, KeyError, json.JSONDecodeError) as error:
            self._send(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": str(error)},
            )
        except Exception as error:
            logger.exception("Supervisor POST failed path=%s", parsed.path)
            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": str(error)},
            )

    def _accepted(self, operation: dict[str, Any]) -> None:
        self._send(
            HTTPStatus.ACCEPTED,
            {"ok": True, "operation": operation},
        )


__all__ = ("SupervisorHTTPServer",)
