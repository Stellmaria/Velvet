from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from velvet_bot.ai_vision import VisionClient

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 5.0
_TEXT_CLIENT_NAMES = frozenset({"VelvetFormattingClient"})
_MODEL_CACHE: dict[tuple[str, str], tuple[float, frozenset[str]]] = {}


@dataclass(frozen=True, slots=True)
class VisionRouteConfig:
    provider: str
    base_url: str
    model: str
    api_key: str | None
    timeout_seconds: int
    candidates: tuple[str, ...]


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


def _task_profile(client_type: type[object]) -> str:
    return str(getattr(client_type, "ai_task_profile", "")).strip().casefold()


def resolve_vision_route(
    client_type: type[object],
    *,
    provider: str,
    base_url: str,
    model: str,
    api_key: str | None,
    timeout_seconds: int,
) -> VisionRouteConfig:
    primary = os.getenv("AI_VISION_MODEL", model).strip() or model
    compare = os.getenv("AI_VISION_COMPARE_MODEL", "").strip()
    fallback = os.getenv("AI_VISION_FALLBACK_MODEL", "").strip()
    profile = _task_profile(client_type)

    if profile == "cascade":
        candidates = _unique_models(model)
    elif profile == "text" or client_type.__name__ in _TEXT_CLIENT_NAMES:
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
    return VisionRouteConfig(
        provider=provider,
        base_url=base_url,
        model=selected,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        candidates=candidates or (selected,),
    )


def configure_client(
    client: "VisionClient",
    *,
    provider: str,
    base_url: str,
    model: str,
    api_key: str | None,
    timeout_seconds: int,
) -> None:
    route = resolve_vision_route(
        type(client),
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    cleaned_provider = route.provider.strip().casefold()
    if cleaned_provider == "local_openai_compatible":
        cleaned_provider = "openai_compatible"
    if cleaned_provider not in {"ollama", "openai_compatible"}:
        raise ValueError("AI_VISION_PROVIDER должен быть ollama или openai_compatible.")
    client.provider = cleaned_provider
    client.base_url = route.base_url.strip().rstrip("/")
    client.model = route.model.strip()
    client.api_key = route.api_key.strip() if route.api_key else None
    client.timeout_seconds = max(10, min(int(route.timeout_seconds), 600))
    if not client.base_url:
        raise ValueError("AI_VISION_BASE_URL не может быть пустым.")
    if not client.model:
        raise ValueError("AI_VISION_MODEL не может быть пустым.")
    client._velvet_model_candidates = route.candidates
    client._velvet_model_cursor = 0
    client._velvet_model_errors = {}


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


def _ollama_models(client: "VisionClient", *, timeout: int) -> frozenset[str] | None:
    if client.provider != "ollama":
        return None
    key = (client.base_url, client.api_key or "")
    now = time.monotonic()
    cached = _MODEL_CACHE.get(key)
    if cached is not None and now - cached[0] <= _CACHE_TTL_SECONDS:
        return cached[1]
    request = urllib.request.Request(
        f"{client.base_url}/api/tags",
        headers=client._headers(),
        method="GET",
    )
    from velvet_bot.ai_vision import VisionAnalysisError

    try:
        payload = client._read_json(request, timeout=min(10, timeout))
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


def routed_read_json(
    client: "VisionClient",
    request: urllib.request.Request,
    *,
    timeout: int,
) -> dict[str, Any]:
    payload = _request_payload(request)
    if payload is None or not str(payload.get("model") or "").strip():
        return client._read_json(request, timeout=timeout)

    candidates = tuple(
        str(value).strip()
        for value in getattr(client, "_velvet_model_candidates", (client.model,))
        if str(value).strip()
    )
    cursor = max(0, int(getattr(client, "_velvet_model_cursor", 0)))
    candidates = candidates[cursor:] or candidates[-1:] or (client.model,)
    available = _ollama_models(client, timeout=timeout)
    if available is not None:
        registered = tuple(model for model in candidates if model.casefold() in available)
        if registered:
            candidates = registered
        else:
            from velvet_bot.ai_vision import VisionAnalysisError
            raise VisionAnalysisError(
                "Ни одна настроенная модель не зарегистрирована в Ollama API: "
                + (", ".join(candidates) or "не заданы")
            )

    errors: dict[str, str] = getattr(client, "_velvet_model_errors", {})
    base_candidates = tuple(
        str(value).strip()
        for value in getattr(client, "_velvet_model_candidates", candidates)
        if str(value).strip()
    )
    from velvet_bot.ai_vision import VisionAnalysisError, VisionProviderUnavailable
    for model in candidates:
        routed_request = _replace_request_model(request, payload, model)
        try:
            result = client._read_json(routed_request, timeout=timeout)
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
        client._velvet_model_cursor = min(index + 1, len(base_candidates))
        client._velvet_model_errors = errors
        return result

    client._velvet_model_errors = errors
    details = "; ".join(f"{model}: {error}" for model, error in errors.items())
    raise VisionAnalysisError(
        "Все настроенные модели отклонили AI-запрос"
        + (f": {details}" if details else ".")
    )


def clear_ai_model_cache() -> None:
    _MODEL_CACHE.clear()


__all__ = (
    "VisionRouteConfig",
    "clear_ai_model_cache",
    "configure_client",
    "resolve_vision_route",
    "routed_read_json",
)
