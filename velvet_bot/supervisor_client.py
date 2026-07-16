from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class SupervisorClientError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SupervisorClient:
    base_url: str
    token: str
    timeout_seconds: int = 20

    async def status(self) -> dict[str, Any]:
        return await self._request("GET", "/v1/status")

    async def logs(self, *, lines: int = 200) -> dict[str, Any]:
        safe_lines = max(1, min(int(lines), 2000))
        query = urllib.parse.urlencode({"lines": safe_lines})
        return await self._request("GET", f"/v1/logs?{query}")

    async def restart(self) -> dict[str, Any]:
        return await self._request("POST", "/v1/restart", {})

    async def update(self) -> dict[str, Any]:
        return await self._request("POST", "/v1/update", {})

    async def rollback(self, target_sha: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if target_sha:
            payload["target_sha"] = target_sha
        return await self._request("POST", "/v1/rollback", payload)

    async def create_codex_task(
        self,
        *,
        prompt: str,
        requested_by: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/codex",
            {"prompt": prompt, "requested_by": requested_by},
        )

    async def codex_task(self, task_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/codex/{task_id}")

    async def apply_codex_task(self, task_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/v1/codex/{task_id}/apply", {})

    async def reject_codex_task(self, task_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/v1/codex/{task_id}/reject", {})

    async def push_codex_task(self, task_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/v1/codex/{task_id}/push", {})

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._request_sync,
            method,
            path,
            payload,
        )

    def _request_sync(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        body = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        )
        request = urllib.request.Request(
            self.base_url.rstrip("/") + path,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            try:
                payload_error = json.loads(raw)
            except json.JSONDecodeError:
                payload_error = {}
            message = payload_error.get("error") if isinstance(payload_error, dict) else None
            raise SupervisorClientError(
                str(message or f"Supervisor вернул HTTP {error.code}.")
            ) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise SupervisorClientError(
                "Velvet Supervisor недоступен. Проверьте, что запущен "
                "`python -m velvet_supervisor` и совпадает SUPERVISOR_TOKEN."
            ) from error
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as error:
            raise SupervisorClientError("Supervisor вернул некорректный JSON.") from error
        if not isinstance(result, dict):
            raise SupervisorClientError("Supervisor вернул неожиданный ответ.")
        if not result.get("ok", False):
            raise SupervisorClientError(str(result.get("error", "Неизвестная ошибка.")))
        return result


def build_supervisor_client() -> SupervisorClient | None:
    enabled = os.getenv("SUPERVISOR_ENABLED", "false").strip().casefold()
    if enabled not in {"1", "true", "yes", "on", "да"}:
        return None
    base_url = os.getenv(
        "SUPERVISOR_BASE_URL",
        "http://127.0.0.1:8765",
    ).strip().rstrip("/")
    token = os.getenv("SUPERVISOR_TOKEN", "").strip()
    if not base_url:
        raise RuntimeError("SUPERVISOR_BASE_URL не может быть пустым.")
    if len(token) < 24:
        raise RuntimeError(
            "SUPERVISOR_TOKEN должен совпадать с токеном Supervisor "
            "и содержать минимум 24 символа."
        )
    raw_timeout = os.getenv("SUPERVISOR_CLIENT_TIMEOUT_SECONDS", "20").strip()
    try:
        timeout = int(raw_timeout)
    except ValueError as error:
        raise RuntimeError(
            "SUPERVISOR_CLIENT_TIMEOUT_SECONDS должен быть целым числом."
        ) from error
    timeout = max(5, min(timeout, 120))
    return SupervisorClient(
        base_url=base_url,
        token=token,
        timeout_seconds=timeout,
    )


__all__ = ("SupervisorClient", "SupervisorClientError", "build_supervisor_client")
