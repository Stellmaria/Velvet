#!/usr/bin/env python3
from __future__ import annotations

import base64
import hmac
import json
import os
from typing import Any, Mapping, Sequence
from urllib.request import Request

import byesu_image_fallback as base
import codex_image_runner as image_runner

_CHEAP_IMAGE_MODEL = "gpt-image-2"
_EXTENDED_IMAGE_MODEL = "firefly-gpt-image-2"
_MAX_REFERENCES = 6
_MAX_REFERENCE_BYTES = 8 * 1024 * 1024
_TARGET_GENERATION_PROMPT_CHARS = 6_500
_MAX_GENERATION_PROMPT_CHARS = 8_000
_INSTALLED = False


def select_image_model(resolution: str, reference_count: int) -> str:
    """Choose the cheapest Byesu generator that satisfies every request field."""
    normalized = resolution.strip().upper()
    if normalized not in base._RESOLUTIONS:
        raise base.ByesuImageFallbackError("Недоступное качество Byesu image route")
    if not 0 <= reference_count <= _MAX_REFERENCES:
        raise base.ByesuImageFallbackError(
            "GPT Image 2 принимает не больше шести референсов"
        )
    if normalized == "1K" and reference_count <= 3:
        return _CHEAP_IMAGE_MODEL
    return _EXTENDED_IMAGE_MODEL


def uses_codex_primary(resolution: str) -> bool:
    """Every supported quality is Codex-first; Byesu is limit fallback only."""
    return resolution.strip().upper() in base._RESOLUTIONS


class RoutedByesuImageClient(base.ByesuImageClient):
    """Split analysis and generation across two distinct Byesu credentials."""

    def __init__(self, *, image_model: str) -> None:
        super().__init__()
        if image_model not in {_CHEAP_IMAGE_MODEL, _EXTENDED_IMAGE_MODEL}:
            raise base.ByesuImageFallbackError(
                "Недоступная модель генерации Byesu для GPT Image 2"
            )
        self.image_model = image_model
        self.analysis_api_key = self.api_key
        self.media_api_key = os.environ.get("BYESU_MEDIA_GEN_API_KEY", "").strip()
        if len(self.media_api_key) < 20:
            raise base.ByesuImageFallbackError(
                "BYESU_MEDIA_GEN_API_KEY не настроен для image generation"
            )
        if hmac.compare_digest(self.analysis_api_key, self.media_api_key):
            raise base.ByesuImageFallbackError(
                "Hermes/Codex и Media Gen должны использовать разные Byesu API keys"
            )

    @property
    def _authorization(self) -> str:
        """Generation endpoints always use the Media Gen credential."""
        return f"Bearer {self.media_api_key}"

    def _json_with_key(
        self,
        path: str,
        *,
        api_key: str,
        method: str = "GET",
        data: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        body = None
        headers = {"Authorization": f"Bearer {api_key}"}
        if data is not None:
            body = json.dumps(
                data,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"
        payload = self._open(
            Request(
                f"{self.base_url}{path}",
                data=body,
                headers=headers,
                method=method,
            )
        )
        try:
            result = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise base.ByesuImageFallbackError(
                "Byesu вернул повреждённый JSON"
            ) from error
        if not isinstance(result, dict):
            raise base.ByesuImageFallbackError(
                "Byesu вернул неожиданный JSON"
            )
        return result

    def _json(
        self,
        path: str,
        *,
        method: str = "GET",
        data: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        """Analysis /responses and analysis capability checks use Hermes key."""
        return self._json_with_key(
            path,
            api_key=self.analysis_api_key,
            method=method,
            data=data,
        )

    def _available_models(self, api_key: str) -> set[str]:
        response = self._json_with_key("/models", api_key=api_key)
        raw_models = response.get("data")
        if not isinstance(raw_models, Sequence):
            return set()
        return {
            str(item.get("id") or "").strip()
            for item in raw_models
            if isinstance(item, Mapping) and item.get("id")
        }

    def assert_capabilities(self, analysis_model: str) -> None:
        if analysis_model not in base._ANALYSIS_MODELS:
            raise base.ByesuImageFallbackError(
                "Недоступная GPT-5.6 модель анализа для Byesu fallback"
            )
        analysis_models = self._available_models(self.analysis_api_key)
        if analysis_model not in analysis_models:
            raise base.ByesuImageFallbackError(
                "Hermes/Codex Byesu key не видит модель анализа: "
                + analysis_model
            )
        media_models = self._available_models(self.media_api_key)
        if self.image_model not in media_models:
            raise base.ByesuImageFallbackError(
                "Media Gen Byesu key не видит модель генерации: "
                + self.image_model
            )

    def analyze(
        self,
        *,
        user_prompt: str,
        references: Sequence[base.ByesuReference],
        analysis_model: str,
        reasoning_effort: str,
        aspect_ratio: str,
        resolution: str,
    ) -> tuple[str, Mapping[str, object] | None]:
        if reasoning_effort not in base._REASONING_EFFORTS:
            raise base.ByesuImageFallbackError(
                "Недоступное reasoning effort для Byesu image route"
            )
        if len(user_prompt.strip()) > _MAX_GENERATION_PROMPT_CHARS:
            raise base.ByesuImageFallbackError(
                "Исходный промт превышает 8000 символов"
            )
        instruction = (
            "Ты являешься visual-reference analyst перед единственной генерацией "
            "изображения. Получи пользовательский промт и все изображения как "
            "единый набор. Уточняй прежде всего внешность: форму лица, глаза, "
            "нос, губы, волосы, возрастной диапазон, телосложение, характерные "
            "детали одежды и аксессуаров. Разрешай противоречия в пользу наиболее "
            "чётких и согласованных изображений. Не заменяй пользовательскую "
            "сцену, действие, композицию, стиль или ограничения своими идеями. "
            "Собери один самодостаточный финальный prompt для image-модели, а не "
            "отчёт об анализе. Не добавляй Markdown, рассуждения, варианты и "
            "пояснения. Не дублируй исходный текст целиком, если его можно сжать "
            "без потери смысла. Не переводи промт на китайский или другой язык "
            "только ради уменьшения числа символов. Сохрани язык пользователя, "
            "кроме общепринятых технических терминов. Целевой объём финального "
            f"prompt: не более {_TARGET_GENERATION_PROMPT_CHARS} символов; "
            f"абсолютный предел: {_MAX_GENERATION_PROMPT_CHARS} символов. "
            "Укажи, что приложенные изображения являются обязательными "
            "визуальными референсами внешности.\n\n"
            f"Целевая пропорция: {aspect_ratio}.\n"
            f"Целевое качество: {resolution}.\n\n"
            f"Пользовательский промт:\n{user_prompt.strip()}"
        )
        content: list[dict[str, object]] = [
            {"type": "input_text", "text": instruction}
        ]
        for reference in references:
            encoded = base64.b64encode(reference.payload).decode("ascii")
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{reference.mime_type};base64,{encoded}",
                    "detail": "original",
                }
            )
        response = self._json(
            "/responses",
            method="POST",
            data={
                "model": analysis_model,
                "reasoning": {"effort": reasoning_effort},
                "input": [{"role": "user", "content": content}],
                "max_output_tokens": 3_500,
            },
        )
        text = self._analysis_text(response)
        if not text:
            raise base.ByesuImageFallbackError(
                "GPT-5.6 анализатор Byesu не вернул финальный prompt"
            )
        if len(text) > _MAX_GENERATION_PROMPT_CHARS:
            raise base.ByesuImageFallbackError(
                "GPT-5.6 анализатор превысил лимит финального prompt 8000 символов"
            )
        usage = response.get("usage")
        return text, usage if isinstance(usage, Mapping) else None

    def run(
        self,
        *,
        user_prompt: str,
        references: Sequence[base.ByesuReference],
        analysis_model: str,
        reasoning_effort: str,
        aspect_ratio: str,
        resolution: str,
    ) -> base.ByesuImageResult:
        expected = select_image_model(resolution, len(references))
        if self.image_model != expected:
            raise base.ByesuImageFallbackError(
                "Выбранная Byesu image-модель не соответствует параметрам запроса"
            )
        if self.image_model == _CHEAP_IMAGE_MODEL:
            if resolution.strip().upper() != "1K" or len(references) > 3:
                raise base.ByesuImageFallbackError(
                    "gpt-image-2 поддерживает только 1K и не больше трёх референсов"
                )
        elif len(references) > _MAX_REFERENCES:
            raise base.ByesuImageFallbackError(
                "firefly-gpt-image-2 принимает не больше шести референсов"
            )
        self.assert_capabilities(analysis_model)
        enhanced_prompt, usage = self.analyze(
            user_prompt=user_prompt,
            references=references,
            analysis_model=analysis_model,
            reasoning_effort=reasoning_effort,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )
        size = base._size_for(resolution, aspect_ratio)
        payload, mime_type, suffix = self.generate(
            prompt=enhanced_prompt,
            references=references,
            size=size,
        )
        return base.ByesuImageResult(
            payload=payload,
            mime_type=mime_type,
            suffix=suffix,
            enhanced_prompt=enhanced_prompt,
            analysis_usage=usage,
            size=size,
            image_model=self.image_model,
        )


def _attempted_routes(
    record: Mapping[str, object],
    *,
    image_model: str,
) -> list[str]:
    attempted = [str(value) for value in record.get("attempted_routes") or []]
    codex_route = f"codex_subscription:{record.get('model') or 'unknown'}"
    if codex_route not in attempted:
        attempted.append(codex_route)
    media_route = f"byesu_media:{image_model}"
    if media_route not in attempted:
        attempted.append(media_route)
    return attempted


def _run_byesu(
    manager: Any,
    run_id: str,
    prompt: str,
    staged: Any,
    *,
    direct: bool,
) -> None:
    """Run Byesu only because Codex subscription is explicitly unavailable."""
    record = manager.store.read(run_id)
    references = base._load_references(record, staged)
    resolution = str(record.get("resolution") or "1K").strip().upper()
    image_model = select_image_model(resolution, len(references))
    attempted = _attempted_routes(record, image_model=image_model)
    route_reason = "codex_limit_preflight" if direct else "subscription_limit"
    event_prefix = (
        "byesu_image_limit_preflight" if direct else "byesu_image_fallback"
    )
    manager.store.update(
        run_id,
        status="running",
        actual_route="byesu_media",
        requested_route="codex_subscription",
        attempted_routes=attempted,
        route_reason=route_reason,
        fallback_reason="subscription_limit",
        codex_generation_skipped=bool(direct),
        last_event={
            "type": f"{event_prefix}_started",
            "analysis_model": record.get("model"),
            "image_model": image_model,
            "automatic_retry": False,
        },
    )
    try:
        client = RoutedByesuImageClient(image_model=image_model)
        result = client.run(
            user_prompt=prompt,
            references=references,
            analysis_model=str(record.get("model") or "gpt-5.6-terra"),
            reasoning_effort=str(record.get("reasoning_effort") or "high"),
            aspect_ratio=str(record.get("aspect_ratio") or "9:16"),
            resolution=resolution,
        )
        artifact = manager._image_artifacts_root() / f"{run_id}{result.suffix}"
        artifact.write_bytes(result.payload)
        artifact.chmod(0o600)
        manager.store.update(
            run_id,
            status="completed",
            finished_at=base.utc_now(),
            artifact_path=str(artifact),
            artifact_name=f"gpt-image-2-byesu-{run_id[:8]}{result.suffix}",
            artifact_mime_type=result.mime_type,
            artifact_bytes=len(result.payload),
            actual_route="byesu_media",
            requested_route="codex_subscription",
            attempted_routes=attempted,
            route_reason=route_reason,
            fallback_reason="subscription_limit",
            codex_generation_skipped=bool(direct),
            provider_model=result.image_model,
            provider_size=result.size,
            analysis_provider="byesu_hermes_codex",
            generation_provider="byesu_media",
            analysis_usage=dict(result.analysis_usage or {}),
            enhanced_prompt_chars=len(result.enhanced_prompt),
            generation_attempts=1,
            last_event={
                "type": f"{event_prefix}_completed",
                "analysis_model": record.get("model"),
                "image_model": result.image_model,
                "size": result.size,
                "automatic_retry": False,
            },
        )
    except Exception as error:
        manager.store.update(
            run_id,
            status="failed",
            finished_at=base.utc_now(),
            actual_route="byesu_media",
            requested_route="codex_subscription",
            attempted_routes=attempted,
            route_reason=route_reason,
            fallback_reason="subscription_limit",
            codex_generation_skipped=bool(direct),
            error=base.redact_text(str(error).strip())[-8_000:]
            or type(error).__name__,
            last_event={
                "type": f"{event_prefix}_failed",
                "error_type": type(error).__name__,
                "automatic_retry": False,
            },
        )


def _run_fallback(manager: Any, run_id: str, prompt: str, staged: Any) -> None:
    _run_byesu(manager, run_id, prompt, staged, direct=False)


def install_byesu_image_routing_policy() -> None:
    """Make every quality Codex-first and install one limit-only Byesu fallback."""
    global _INSTALLED
    if _INSTALLED:
        return
    image_runner.MAX_IMAGE_REFERENCES = _MAX_REFERENCES
    image_runner.MAX_IMAGE_REFERENCE_BYTES = _MAX_REFERENCE_BYTES
    image_runner.MAX_IMAGE_TOTAL_REFERENCE_BYTES = (
        _MAX_REFERENCES * _MAX_REFERENCE_BYTES
    )
    base._run_fallback = _run_fallback
    _INSTALLED = True


__all__ = (
    "RoutedByesuImageClient",
    "install_byesu_image_routing_policy",
    "select_image_model",
    "uses_codex_primary",
)
