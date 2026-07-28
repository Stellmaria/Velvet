from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from threading import Lock
from typing import Any

from velvet_bot.ai_vision import (
    VisionAnalysisError,
    VisionClient,
    VisionProviderUnavailable,
)

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 5.0
_TEXT_CLIENT_NAMES = frozenset({"VelvetFormattingClient"})
_INSTALL_LOCK = Lock()
_INSTALLED = False
_ORIGINAL_INIT = VisionClient.__init__
_ORIGINAL_READ_JSON = VisionClient._read_json
_MODEL_CACHE: dict[tuple[str, str], tuple[float, frozenset[str]]] = {}


def _unique_models(*values: str) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value or "").strip()
        identity = cleaned.casefold()
        if not cleaned or identity in seen:
            continue
        seen.add(identity)
        result.append(cleaned)
    return tuple(result)


def _bounded_timeout(value: str, *, default: int) -> int:
    try:
        parsed = int(value.strip())
    except (AttributeError, TypeError, ValueError):
        return default
    return max(10, min(parsed, 600))


def _is_text_client(client: VisionClient) -> bool:
    explicit = str(getattr(type(client), "ai_task_profile", "")).strip().casefold()
    return explicit == "text" or type(client).__name__ in _TEXT_CLIENT_NAMES


def _configure_client(
    client: VisionClient,
    *,
    provider: str,
    base_url: str,
    model: str,
    api_key: str | None,
    timeout_seconds: int,
) -> None:
    primary = os.getenv("AI_VISION_MODEL", model).strip() or model
    compare = os.getenv("AI_VISION_COMPARE_MODEL", "").strip()
    fallback = os.getenv("AI_VISION_FALLBACK_MODEL", "").strip()

    if _is_text_client(client):
        provider = os.getenv("AI_TEXT_PROVIDER", provider).strip() or provider
        base_url = os.getenv("AI_TEXT_BASE_URL", base_url).strip() or base_url
        api_key = os.getenv("AI_TEXT_API_KEY", "").strip() or api_key
        timeout_seconds = _bounded_timeout(
            os.getenv("AI_TEXT_TIMEOUT_SECONDS", str(timeout_seconds)),
            default=timeout_seconds,
        )
        text_model = os.getenv("AI_TEXT_MODEL", "").strip()
        candidates = _unique_models(text_model, compare, primary, fallback, model)
    else:
        candidates = _unique_models(model, primary, compare, fallback)

    selected = candidates[0] if candidates else model
    _ORIGINAL_INIT(
        client,
        provider=provider,
        base_url=base_url,
        model=selected,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    client._velvet_model_candidates = candidates or (selected,)  # type: ignore[attr-defined]
    client._velvet_model_cursor = 0  # type: ignore[attr-defined]
    client._velvet_model_errors = {}  # type: ignore[attr-defined]


def _request_payload(request: urllib.request.Request) -> dict[str, Any] | None:
    raw = request.data
    if not raw:
        return None
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _replace_request_model(
    request: urllib.request.Request,
    payload: dict[str, Any],
    model: str,
) -> urllib.request.Request:
    updated = dict(payload)
    updated["model"] = model
    return urllib.request.Request(
        request.full_url,
        data=json.dumps(updated, ensure_ascii=False).encode("utf-8"),
        headers=dict(request.header_items()),
        method=request.get_method(),
    )


def _ollama_models(client: VisionClient, *, timeout: int) -> frozenset[str] | None:
    if client.provider != "ollama":
        return None
    authorization = client.api_key or ""
    key = (client.base_url, authorization)
    now = time.monotonic()
    cached = _MODEL_CACHE.get(key)
    if cached is not None and now - cached[0] <= _CACHE_TTL_SECONDS:
        return cached[1]

    request = urllib.request.Request(
        f"{client.base_url}/api/tags",
        headers=client._headers(),
        method="GET",
    )
    try:
        payload = _ORIGINAL_READ_JSON(request, timeout=min(10, timeout))
    except VisionAnalysisError:
        return None

    names: set[str] = set()
    models = payload.get("models")
    if isinstance(models, list):
        for item in models:
            if not isinstance(item, dict):
                continue
            for field in ("name", "model"):
                value = str(item.get(field) or "").strip()
                if value:
                    names.add(value.casefold())
    result = frozenset(names)
    _MODEL_CACHE[key] = (now, result)
    return result


def _ordered_candidates(client: VisionClient) -> tuple[str, ...]:
    candidates = tuple(
        str(value).strip()
        for value in getattr(client, "_velvet_model_candidates", (client.model,))
        if str(value).strip()
    )
    cursor = max(0, int(getattr(client, "_velvet_model_cursor", 0)))
    if cursor >= len(candidates):
        return candidates[-1:] if candidates else (client.model,)
    return candidates[cursor:]


def _routed_read_json(
    client: VisionClient,
    request: urllib.request.Request,
    *,
    timeout: int,
) -> dict[str, Any]:
    payload = _request_payload(request)
    if payload is None or not str(payload.get("model") or "").strip():
        return _ORIGINAL_READ_JSON(request, timeout=timeout)

    candidates = _ordered_candidates(client)
    available = _ollama_models(client, timeout=timeout)
    if available is not None:
        registered = tuple(model for model in candidates if model.casefold() in available)
        if registered:
            candidates = registered
        else:
            configured = ", ".join(candidates) or "не заданы"
            raise VisionAnalysisError(
                "Ни одна настроенная модель не зарегистрирована в Ollama API: "
                + configured
            )

    errors: dict[str, str] = getattr(client, "_velvet_model_errors", {})
    base_candidates = tuple(
        str(value).strip()
        for value in getattr(client, "_velvet_model_candidates", candidates)
        if str(value).strip()
    )
    for model in candidates:
        routed_request = _replace_request_model(request, payload, model)
        try:
            result = _ORIGINAL_READ_JSON(routed_request, timeout=timeout)
        except VisionProviderUnavailable:
            raise
        except VisionAnalysisError as error:
            errors[model] = str(error)[:500]
            logger.info("AI model route failed model=%s error=%s", model, errors[model])
            continue

        client.model = model
        try:
            index = base_candidates.index(model)
        except ValueError:
            index = 0
        client._velvet_model_cursor = min(index + 1, len(base_candidates))  # type: ignore[attr-defined]
        client._velvet_model_errors = errors  # type: ignore[attr-defined]
        return result

    client._velvet_model_errors = errors  # type: ignore[attr-defined]
    details = "; ".join(f"{model}: {error}" for model, error in errors.items())
    raise VisionAnalysisError(
        "Все настроенные модели отклонили AI-запрос"
        + (f": {details}" if details else ".")
    )


def install_ai_model_routing() -> None:
    """Install one routing layer for every VisionClient-derived bot task."""

    global _INSTALLED
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        VisionClient.__init__ = _configure_client  # type: ignore[method-assign]
        VisionClient._read_json = _routed_read_json  # type: ignore[method-assign]
        _INSTALLED = True


def clear_ai_model_cache() -> None:
    _MODEL_CACHE.clear()


__all__ = (
    "clear_ai_model_cache",
    "install_ai_model_routing",
)
