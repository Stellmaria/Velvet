from __future__ import annotations

import asyncio
import base64
import json
import urllib.request
from typing import Any

from velvet_bot.ai_vision import (
    MediaAIRepository,
    VisionAnalysisError,
    VisionAnalysisTarget,
    VisionClient,
    _ANALYSIS_PROMPT,
    _PROFILE_SCHEMA,
    _extract_json_object,
    _prepare_image,
    normalize_ai_profile,
)
from velvet_bot.database import Database

_RESPONSE_VERSION = 2
_SCHEMA_PROMPT = (
    _ANALYSIS_PROMPT
    + "\n\nСтрого заполни один JSON-объект по этой JSON Schema. "
    + "Не добавляй markdown, пояснения или текст вне JSON:\n"
    + json.dumps(_PROFILE_SCHEMA, ensure_ascii=False, separators=(",", ":"))
)


def _response_diagnostic(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if not isinstance(message, dict):
        message = {}
    content = str(message.get("content") or "")
    thinking = str(message.get("thinking") or "")
    response = str(payload.get("response") or "")
    return (
        f"content={len(content)}, thinking={len(thinking)}, "
        f"response={len(response)}, done_reason={payload.get('done_reason')!r}, "
        f"eval_count={payload.get('eval_count')!r}"
    )


def _parse_ollama_payload(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message")
    if not isinstance(message, dict):
        message = {}

    candidates = (
        ("content", message.get("content")),
        ("thinking", message.get("thinking")),
        ("response", payload.get("response")),
    )
    parse_errors: list[str] = []
    for source, value in candidates:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            return normalize_ai_profile(_extract_json_object(text))
        except VisionAnalysisError as error:
            parse_errors.append(f"{source}: {error}")

    details = _response_diagnostic(payload)
    if parse_errors:
        details += "; " + "; ".join(parse_errors)
    raise VisionAnalysisError(f"Qwen не вернул пригодный JSON ({details}).")


class ReliableVisionClient(VisionClient):
    """Ollama vision client with schema grounding and a JSON-mode fallback."""

    async def _ollama_request(
        self,
        *,
        image_base64: str,
        use_schema: bool,
    ) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": _SCHEMA_PROMPT,
                    "images": [image_base64],
                }
            ],
            "format": _PROFILE_SCHEMA if use_schema else "json",
            "stream": False,
            "think": False,
            "keep_alive": "15m",
            "options": {
                "temperature": 0,
                "num_predict": 1600,
            },
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        return await asyncio.to_thread(
            self._read_json,
            request,
            timeout=self.timeout_seconds,
        )

    async def analyze(self, source: bytes) -> dict[str, Any]:
        if self.provider != "ollama":
            return await super().analyze(source)

        prepared = await asyncio.to_thread(_prepare_image, source)
        image_base64 = base64.b64encode(prepared).decode("ascii")
        diagnostics: list[str] = []

        for use_schema in (True, False):
            payload = await self._ollama_request(
                image_base64=image_base64,
                use_schema=use_schema,
            )
            try:
                return _parse_ollama_payload(payload)
            except VisionAnalysisError as error:
                mode = "schema" if use_schema else "json"
                diagnostics.append(f"{mode}: {error}")

        raise VisionAnalysisError(
            "Qwen не вернул JSON после двух режимов Ollama. "
            + " | ".join(diagnostics)
        )


class ReliableMediaAIRepository(MediaAIRepository):
    """Requeue old formatting failures once and mark new attempts as version 2."""

    def __init__(self, database: Database) -> None:
        super().__init__(database)

    async def claim_targets(
        self,
        *,
        provider: str,
        model: str,
        max_attempts: int,
        limit: int = 1,
    ) -> tuple[VisionAnalysisTarget, ...]:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE media_ai_profiles
                SET status = 'pending',
                    attempt_count = 0,
                    error_message = NULL,
                    analyzed_at = NULL,
                    updated_at = NOW()
                WHERE analysis_version < $1::SMALLINT
                  AND status IN ('error', 'skipped')
                  AND (
                        error_message = 'ИИ не вернул JSON.'
                        OR error_message LIKE 'Ответ ИИ содержит повреждённый JSON.%'
                        OR error_message LIKE 'Qwen не вернул пригодный JSON%'
                        OR error_message LIKE 'Qwen не вернул JSON после двух режимов%'
                      )
                """,
                _RESPONSE_VERSION,
            )

        targets = await super().claim_targets(
            provider=provider,
            model=model,
            max_attempts=max_attempts,
            limit=limit,
        )
        if targets:
            async with self._database.acquire() as connection:
                await connection.execute(
                    """
                    UPDATE media_ai_profiles
                    SET analysis_version = $2::SMALLINT,
                        updated_at = NOW()
                    WHERE media_id = ANY($1::BIGINT[])
                    """,
                    [target.media_id for target in targets],
                    _RESPONSE_VERSION,
                )
        return targets


__all__ = (
    "ReliableMediaAIRepository",
    "ReliableVisionClient",
)
