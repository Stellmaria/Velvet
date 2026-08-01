#!/usr/bin/env python3
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

logger = logging.getLogger("velvet.hermes_coder_router")
_MAX_BODY_BYTES = 32_768
_TASK_ID = re.compile(r"^[a-f0-9]{32}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{3,160}$")
_SECRET_KEY = re.compile(r"(?i)(token|secret|password|api[_-]?key|authorization)")
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY)[A-Z0-9_]*\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
)


@dataclass(frozen=True, slots=True)
class CoderTarget:
    project: str
    repository: str
    bot_handle: str
    base_url: str
    token: str


class RouterError(RuntimeError):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def _redact_text(value: str) -> str:
    result = value
    for pattern in _SECRET_TEXT_PATTERNS:
        if pattern.groups:
            result = pattern.sub(r"\1[REDACTED]", result)
        else:
            result = pattern.sub("[REDACTED]", result)
    return result


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _env_required(name: str, *, minimum: int = 24) -> str:
    value = os.getenv(name, "").strip()
    if len(value) < minimum:
        raise RuntimeError(f"{name} отсутствует или короче {minimum} символов")
    return value


def load_targets() -> dict[str, CoderTarget]:
    return {
        "velvet": CoderTarget(
            project="velvet",
            repository="Stellmaria/Velvet",
            bot_handle="@velvet_private_coder_bot",
            base_url=os.getenv(
                "HERMES_CODER_VELVET_BASE_URL",
                "http://hermes-coder-velvet:8642",
            ).strip().rstrip("/"),
            token=os.getenv("HERMES_CODER_VELVET_TOKEN", "").strip(),
        ),
        "max": CoderTarget(
            project="max",
            repository="Stellmaria/romatic_club_bot_max",
            bot_handle="@romatic_max_coder_bot",
            base_url=os.getenv(
                "HERMES_CODER_MAX_BASE_URL",
                "http://hermes-coder-max:8642",
            ).strip().rstrip("/"),
            token=os.getenv("HERMES_CODER_MAX_TOKEN", "").strip(),
        ),
    }


def build_task_prompt(target: CoderTarget, *, task_id: str, task: str, source: str) -> str:
    clean_task = _redact_text(task).strip()
    if not clean_task:
        raise RouterError(HTTPStatus.BAD_REQUEST, "Текст задачи пуст.")
    if len(clean_task) > 24_000:
        raise RouterError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Текст задачи превышает 24000 символов.")
    return f"""ОРКЕСТРИРОВАННАЯ ЗАДАЧА

Task ID: {task_id}
Источник: {source}
Проект: {target.project}
Репозиторий: {target.repository}
Coder: {target.bot_handle}

Задача:
{clean_task}

Обязательный порядок:
1. Подтверди, что `/workspace` является checkout `{target.repository}` и получи актуальное состояние `origin/main`.
2. Создай отдельную ветку `agent/<краткое-название>` от актуального `origin/main`. Не работай в `main`.
3. Исследуй проблему, внеси минимальное исправление и добавь regression-тесты.
4. Запусти релевантные тесты, type check и сборочные проверки.
5. Проверь diff и отсутствие секретов, `.env`, дампов, runtime-файлов и несвязанных изменений.
6. Сделай commit, push и создай один pull request в `main`. Не сливай его.
7. В финальном ответе укажи отдельными строками:
   STATUS: completed|blocked|failed
   BRANCH: <ветка или none>
   PR: <URL или none>
   TESTS: <краткий результат>
   BLOCKER: <причина или none>

Запрещено: Docker socket, systemd, root/sudo, production checkout, изменение production БД, чтение секретов, merge, deployment, restart/update/rollback.
"""


class CoderRouter:
    def __init__(self) -> None:
        self.client_token = _env_required("HERMES_CODER_ROUTER_CLIENT_TOKEN")
        self.targets = load_targets()
        self.timeout_seconds = max(
            3,
            min(120, int(os.getenv("HERMES_CODER_ROUTER_TIMEOUT_SECONDS", "30"))),
        )

    def configured(self, project: str) -> bool:
        target = self.targets.get(project)
        return bool(target and len(target.token) >= 24 and target.base_url)

    def authenticate(self, authorization: str | None) -> None:
        prefix = "Bearer "
        if not authorization or not authorization.startswith(prefix):
            raise RouterError(HTTPStatus.UNAUTHORIZED, "Требуется Bearer token.")
        candidate = authorization[len(prefix) :].strip()
        if not hmac.compare_digest(candidate, self.client_token):
            raise RouterError(HTTPStatus.FORBIDDEN, "Неверный client token.")

    def _target(self, project: str) -> CoderTarget:
        target = self.targets.get(project)
        if target is None:
            raise RouterError(HTTPStatus.NOT_FOUND, "Неизвестный проект.")
        if not self.configured(project):
            raise RouterError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                f"Coder {project} ещё не подключён к router.",
            )
        return target

    def upstream(
        self,
        target: CoderTarget,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = None
        headers = {
            "Authorization": f"Bearer {target.token}",
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{target.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")[:2000]
            raise RouterError(
                HTTPStatus.BAD_GATEWAY,
                f"Coder {target.project} вернул HTTP {error.code}: {_redact_text(details)}",
            ) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RouterError(
                HTTPStatus.BAD_GATEWAY,
                f"Coder {target.project} недоступен: {error}",
            ) from error
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RouterError(
                HTTPStatus.BAD_GATEWAY,
                f"Coder {target.project} вернул повреждённый JSON.",
            ) from error
        if not isinstance(result, dict):
            raise RouterError(
                HTTPStatus.BAD_GATEWAY,
                f"Coder {target.project} вернул неожиданный тип ответа.",
            )
        return redact(result)

    def capabilities(self, project: str) -> dict[str, Any]:
        return self.upstream(self._target(project), "GET", "/v1/capabilities")

    def submit(self, project: str, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"task_id", "task", "source"}:
            raise RouterError(
                HTTPStatus.BAD_REQUEST,
                "Допустимы только task_id, task и source.",
            )
        task_id = payload.get("task_id")
        task = payload.get("task")
        source = payload.get("source")
        if not isinstance(task_id, str) or not _TASK_ID.fullmatch(task_id):
            raise RouterError(HTTPStatus.BAD_REQUEST, "Некорректный task_id.")
        if not isinstance(task, str):
            raise RouterError(HTTPStatus.BAD_REQUEST, "task должен быть строкой.")
        if not isinstance(source, str) or not source.strip() or len(source) > 128:
            raise RouterError(HTTPStatus.BAD_REQUEST, "Некорректный source.")
        target = self._target(project)
        prompt = build_task_prompt(
            target,
            task_id=task_id,
            task=task,
            source=_redact_text(source).strip(),
        )
        result = self.upstream(
            target,
            "POST",
            "/v1/runs",
            {
                "input": prompt,
                "session_id": f"orchestration-{project}-{task_id}",
                "instructions": (
                    "Ты изолированный coder-агент. Работай только в указанном "
                    "репозитории, создай ветку и pull request, не меняй production."
                ),
            },
        )
        return {**result, "task_id": task_id, "project": project}

    def run_status(self, project: str, run_id: str) -> dict[str, Any]:
        self._validate_run_id(run_id)
        return self.upstream(self._target(project), "GET", f"/v1/runs/{run_id}")

    def stop(self, project: str, run_id: str) -> dict[str, Any]:
        self._validate_run_id(run_id)
        return self.upstream(
            self._target(project),
            "POST",
            f"/v1/runs/{run_id}/stop",
            {},
        )

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if not _RUN_ID.fullmatch(run_id):
            raise RouterError(HTTPStatus.BAD_REQUEST, "Некорректный run_id.")


class Handler(BaseHTTPRequestHandler):
    server_version = "HermesCoderRouter/1.0"

    @property
    def router(self) -> CoderRouter:
        return self.server.router  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        logger.info("coder-router http: " + format, *args)

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(redact(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise RouterError(HTTPStatus.BAD_REQUEST, "Некорректный Content-Length.") from error
        if length < 0 or length > _MAX_BODY_BYTES:
            raise RouterError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Слишком большой запрос.")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError as error:
            raise RouterError(HTTPStatus.BAD_REQUEST, "Повреждённый JSON.") from error
        if not isinstance(payload, dict):
            raise RouterError(HTTPStatus.BAD_REQUEST, "JSON body должен быть объектом.")
        return payload

    def _auth(self) -> None:
        self.router.authenticate(self.headers.get("Authorization"))

    def do_GET(self) -> None:  # noqa: N802
        try:
            if self.path == "/health":
                configured = {
                    project: self.router.configured(project)
                    for project in self.router.targets
                }
                status = "ok" if all(configured.values()) else "degraded"
                self._json(HTTPStatus.OK, {"status": status, "coders": configured})
                return
            self._auth()
            parts = [part for part in self.path.split("?")[0].split("/") if part]
            if len(parts) == 4 and parts[:2] == ["v1", "coders"] and parts[3] == "capabilities":
                self._json(HTTPStatus.OK, self.router.capabilities(parts[2]))
                return
            if len(parts) == 5 and parts[:2] == ["v1", "coders"] and parts[3] == "runs":
                self._json(HTTPStatus.OK, self.router.run_status(parts[2], parts[4]))
                return
            raise RouterError(HTTPStatus.NOT_FOUND, "Маршрут не найден.")
        except RouterError as error:
            self._json(error.status, {"ok": False, "error": str(error)})
        except Exception:
            logger.exception("Unhandled coder router GET error")
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "Внутренняя ошибка router."})

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._auth()
            parts = [part for part in self.path.split("?")[0].split("/") if part]
            if len(parts) == 4 and parts[:2] == ["v1", "coders"] and parts[3] == "runs":
                self._json(HTTPStatus.ACCEPTED, self.router.submit(parts[2], self._body()))
                return
            if len(parts) == 6 and parts[:2] == ["v1", "coders"] and parts[3] == "runs" and parts[5] == "stop":
                if self._body() != {}:
                    raise RouterError(HTTPStatus.BAD_REQUEST, "stop принимает только пустой JSON.")
                self._json(HTTPStatus.ACCEPTED, self.router.stop(parts[2], parts[4]))
                return
            raise RouterError(HTTPStatus.NOT_FOUND, "Маршрут не найден.")
        except RouterError as error:
            self._json(error.status, {"ok": False, "error": str(error)})
        except Exception:
            logger.exception("Unhandled coder router POST error")
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "Внутренняя ошибка router."})


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    host = os.getenv("HERMES_CODER_ROUTER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.getenv("HERMES_CODER_ROUTER_PORT", "8878"))
    router = CoderRouter()
    server = ThreadingHTTPServer((host, port), Handler)
    server.router = router  # type: ignore[attr-defined]
    logger.info("Hermes coder router listening on %s:%s", host, port)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
