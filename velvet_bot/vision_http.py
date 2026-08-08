from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping

from aiohttp import ClientError, ClientSession, ClientTimeout

from velvet_bot.vision_failures import (
    VisionProviderError,
    VisionTimeoutError,
    VisionTransportError,
    classify_http_failure,
    classify_payload_failure,
)


def _error_detail(payload: object, raw_text: str) -> str:
    if isinstance(payload, Mapping):
        value = payload.get("error")
        if isinstance(value, Mapping):
            nested = value.get("message") or value.get("detail") or value.get("error")
            if nested:
                return str(nested).strip()[:1200]
        if value:
            return str(value).strip()[:1200]
        for key in ("message", "detail"):
            value = payload.get(key)
            if value:
                return str(value).strip()[:1200]
    return raw_text.strip()[:1200]


async def post_vision_json(
    *,
    url: str,
    body: Mapping[str, object],
    headers: Mapping[str, str],
    timeout_seconds: int,
) -> dict[str, object]:
    """POST one VL request with real asyncio cancellation and typed failures."""

    timeout = ClientTimeout(total=max(1, int(timeout_seconds)))
    try:
        async with ClientSession(timeout=timeout, raise_for_status=False) as session:
            async with session.post(
                url,
                json=dict(body),
                headers=dict(headers),
            ) as response:
                status = int(response.status)
                raw = await response.text()
    except asyncio.CancelledError:
        # Closing the aiohttp context aborts the downstream HTTP request. Never turn
        # cancellation into a retryable provider failure.
        raise
    except asyncio.TimeoutError as error:
        raise VisionTimeoutError(
            f"VL request timed out after {int(timeout_seconds)}s."
        ) from error
    except ClientError as error:
        raise VisionTransportError(f"VL transport failed: {error}") from error
    except OSError as error:
        raise VisionTransportError(f"VL transport failed: {error}") from error

    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as error:
        raise VisionProviderError(
            f"VL provider вернул некорректный JSON HTTP-ответ status={status}."
        ) from error
    if not isinstance(payload, dict):
        raise VisionProviderError(
            f"VL provider вернул неожиданный HTTP payload status={status}."
        )

    detail = _error_detail(payload, raw)
    if status >= 400:
        raise classify_http_failure(status=status, detail=detail)
    if payload.get("error"):
        raise classify_payload_failure(detail)
    return dict(payload)


__all__ = ("post_vision_json",)
