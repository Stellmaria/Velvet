from __future__ import annotations

import asyncio
import json
from typing import cast

import aiohttp

from velvet_bot.domains.telegram_storage.librarian_models import (
    HermesRunResult,
    JsonObject,
    StorageLibrarianError,
    StorageLibrarianSettings,
)

_TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "canceled"}


def _json_object(value: object) -> JsonObject:
    if isinstance(value, dict):
        return cast(JsonObject, dict(value))
    return {}


class HermesRunsClient:
    def __init__(self, settings: StorageLibrarianSettings) -> None:
        self._settings = settings

    def _headers(self) -> dict[str, str]:
        api_key = self._settings.hermes_api_key
        if api_key is None:
            raise StorageLibrarianError("HERMES_API_KEY не настроен.")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def run(
        self,
        *,
        prompt: str,
        session_id: str,
        instructions: str,
    ) -> HermesRunResult:
        timeout = aiohttp.ClientTimeout(total=self._settings.run_timeout_seconds)
        async with aiohttp.ClientSession(
            timeout=timeout,
            headers=self._headers(),
        ) as session:
            run_id = await self._create_run(
                session,
                prompt=prompt,
                session_id=session_id,
                instructions=instructions,
            )
            return await self._wait_for_run(session, run_id)

    async def _create_run(
        self,
        session: aiohttp.ClientSession,
        *,
        prompt: str,
        session_id: str,
        instructions: str,
    ) -> str:
        try:
            async with session.post(
                f"{self._settings.hermes_base_url}/v1/runs",
                json={
                    "input": prompt,
                    "session_id": session_id,
                    "instructions": instructions,
                },
            ) as response:
                payload = await self._json_response(response)
                if response.status not in {200, 201, 202}:
                    raise StorageLibrarianError(
                        f"Hermes POST /v1/runs вернул HTTP {response.status}: "
                        f"{payload!r}"
                    )
        except asyncio.CancelledError:
            raise
        except (aiohttp.ClientError, TimeoutError, OSError) as error:
            raise StorageLibrarianError(f"Hermes Runs API недоступен: {error}") from error

        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise StorageLibrarianError("Hermes не вернул run_id.")
        return run_id.strip()

    async def _wait_for_run(
        self,
        session: aiohttp.ClientSession,
        run_id: str,
    ) -> HermesRunResult:
        deadline = asyncio.get_running_loop().time() + self._settings.run_timeout_seconds
        while True:
            if asyncio.get_running_loop().time() >= deadline:
                raise StorageLibrarianError(
                    f"Hermes run {run_id} не завершился вовремя."
                )
            await asyncio.sleep(self._settings.poll_interval_seconds)
            try:
                async with session.get(
                    f"{self._settings.hermes_base_url}/v1/runs/{run_id}"
                ) as response:
                    payload = await self._json_response(response)
                    if response.status != 200:
                        raise StorageLibrarianError(
                            f"Hermes GET run вернул HTTP {response.status}: {payload!r}"
                        )
            except asyncio.CancelledError:
                raise
            except StorageLibrarianError:
                raise
            except (aiohttp.ClientError, TimeoutError, OSError) as error:
                raise StorageLibrarianError(
                    f"Не удалось получить Hermes run {run_id}: {error}"
                ) from error

            status = str(payload.get("status") or "").casefold()
            if status not in _TERMINAL_RUN_STATUSES:
                continue
            if status != "completed":
                raise StorageLibrarianError(
                    f"Hermes run {run_id} завершился со статусом {status}: "
                    f"{payload.get('error') or 'без описания'}"
                )
            output = payload.get("output")
            if not isinstance(output, str) or not output.strip():
                raise StorageLibrarianError(
                    f"Hermes run {run_id} не вернул текст результата."
                )
            return HermesRunResult(
                run_id=run_id,
                output=output.strip(),
                usage=_json_object(payload.get("usage")),
            )

    @staticmethod
    async def _json_response(response: aiohttp.ClientResponse) -> JsonObject:
        text = await response.text()
        try:
            decoded: object = json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text[:2000]}
        if isinstance(decoded, dict):
            return cast(JsonObject, decoded)
        return {"value": str(decoded)[:2000]}


__all__ = ("HermesRunsClient",)
