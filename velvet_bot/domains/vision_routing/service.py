from __future__ import annotations

import asyncio
import hashlib
from typing import Mapping

from velvet_bot.ai_vision import VisionAnalysisError, _prepare_image
from velvet_bot.domains.vision_routing.cache import VisionAnalysisCacheRepository
from velvet_bot.domains.vision_routing.client import MeteredVisionClient
from velvet_bot.domains.vision_routing.models import (
    CachedVisionAnalysis,
    VisionCascadeResult,
    VisionProviderAnalysis,
    VisionRoute,
)

_REFUSAL_MARKERS = (
    "provider refusal",
    "content policy",
    "safety policy",
    "moderation",
    "request was blocked",
    "content was blocked",
    "cannot analyze this image",
    "can't analyze this image",
    "nsfw",
)


class VisionCascadeRouter:
    def __init__(
        self,
        *,
        flash: MeteredVisionClient,
        repository: VisionAnalysisCacheRepository,
        pro: MeteredVisionClient | None = None,
        sensitive: MeteredVisionClient | None = None,
        confidence_threshold: int = 70,
        prompt_version: int = 1,
        analysis_type: str = "semantic-profile",
    ) -> None:
        self._flash = flash
        self._pro = pro
        self._sensitive = sensitive
        self._repository = repository
        self.confidence_threshold = max(1, min(int(confidence_threshold), 100))
        self.prompt_version = max(1, int(prompt_version))
        self.analysis_type = analysis_type.strip()
        if not self.analysis_type:
            raise ValueError("Vision analysis_type не может быть пустым.")

    @property
    def provider(self) -> str:
        return self._flash.provider

    @property
    def model(self) -> str:
        return self._flash.model

    @property
    def configured_models(self) -> tuple[str, ...]:
        clients = (self._flash, self._pro, self._sensitive)
        return tuple(
            dict.fromkeys(client.model for client in clients if client is not None)
        )

    async def health(self) -> bool:
        return await self._flash.health()

    async def analyze(
        self,
        source: bytes,
        *,
        sensitive: bool = False,
        user_id: int | None = None,
        chat_id: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> VisionCascadeResult:
        content_hash = hashlib.sha256(source).hexdigest()
        cached = await self._repository.find(
            content_hash=content_hash,
            analysis_type=self.analysis_type,
            prompt_version=self.prompt_version,
            models=self._cache_models(sensitive=sensitive),
        )
        if cached is not None:
            return _cached_result(cached)

        prepared = await asyncio.to_thread(_prepare_image, source)
        common_metadata = {
            "content_hash": content_hash,
            "analysis_type": self.analysis_type,
            "prompt_version": self.prompt_version,
            **dict(metadata or {}),
        }
        attempts: list[VisionRoute] = []

        if sensitive:
            if self._sensitive is None:
                raise VisionAnalysisError("Sensitive VL route не настроен.")
            analysis = await self._call(
                self._sensitive,
                prepared,
                attempts=attempts,
                user_id=user_id,
                chat_id=chat_id,
                metadata=common_metadata,
            )
            return await self._accept(
                analysis,
                content_hash=content_hash,
                attempts=attempts,
                metadata={"explicit_sensitive": True},
            )

        flash_error: VisionAnalysisError | None = None
        flash_analysis: VisionProviderAnalysis | None = None
        try:
            flash_analysis = await self._call(
                self._flash,
                prepared,
                attempts=attempts,
                user_id=user_id,
                chat_id=chat_id,
                metadata=common_metadata,
            )
        except VisionAnalysisError as error:
            flash_error = error
            if _is_refusal(error) and self._sensitive is not None:
                sensitive_analysis = await self._call(
                    self._sensitive,
                    prepared,
                    attempts=attempts,
                    user_id=user_id,
                    chat_id=chat_id,
                    metadata={**common_metadata, "fallback_reason": "flash_refusal"},
                )
                return await self._accept(
                    sensitive_analysis,
                    content_hash=content_hash,
                    attempts=attempts,
                    metadata={"fallback_reason": "flash_refusal"},
                )
            if self._pro is None:
                raise

        if flash_analysis is not None:
            confidence = _confidence(flash_analysis.profile)
            if confidence >= self.confidence_threshold or self._pro is None:
                return await self._accept(
                    flash_analysis,
                    content_hash=content_hash,
                    attempts=attempts,
                    metadata={
                        "confidence_threshold": self.confidence_threshold,
                        "pro_required": False,
                    },
                )

        if self._pro is None:
            if flash_error is not None:
                raise flash_error
            raise VisionAnalysisError("Pro VL route не настроен.")

        try:
            pro_analysis = await self._call(
                self._pro,
                prepared,
                attempts=attempts,
                user_id=user_id,
                chat_id=chat_id,
                metadata={
                    **common_metadata,
                    "fallback_reason": (
                        "flash_error" if flash_error is not None else "low_confidence"
                    ),
                    "flash_confidence": (
                        _confidence(flash_analysis.profile)
                        if flash_analysis is not None
                        else None
                    ),
                },
            )
        except VisionAnalysisError as error:
            if _is_refusal(error) and self._sensitive is not None:
                sensitive_analysis = await self._call(
                    self._sensitive,
                    prepared,
                    attempts=attempts,
                    user_id=user_id,
                    chat_id=chat_id,
                    metadata={**common_metadata, "fallback_reason": "pro_refusal"},
                )
                return await self._accept(
                    sensitive_analysis,
                    content_hash=content_hash,
                    attempts=attempts,
                    metadata={"fallback_reason": "pro_refusal"},
                )
            if flash_analysis is not None:
                return await self._accept(
                    flash_analysis,
                    content_hash=content_hash,
                    attempts=attempts,
                    metadata={
                        "fallback_reason": "pro_error_use_flash",
                        "pro_error": str(error)[:500],
                    },
                )
            raise

        return await self._accept(
            pro_analysis,
            content_hash=content_hash,
            attempts=attempts,
            metadata={
                "fallback_reason": (
                    "flash_error" if flash_error is not None else "low_confidence"
                ),
                "confidence_threshold": self.confidence_threshold,
            },
        )

    async def _call(
        self,
        client: MeteredVisionClient,
        prepared: bytes,
        *,
        attempts: list[VisionRoute],
        user_id: int | None,
        chat_id: int | None,
        metadata: Mapping[str, object],
    ) -> VisionProviderAnalysis:
        attempts.append(client.route)
        return await client.analyze_prepared(
            prepared,
            user_id=user_id,
            chat_id=chat_id,
            operation=f"vision.{self.analysis_type}.{client.route.value}",
            metadata=metadata,
        )

    async def _accept(
        self,
        analysis: VisionProviderAnalysis,
        *,
        content_hash: str,
        attempts: list[VisionRoute],
        metadata: Mapping[str, object],
    ) -> VisionCascadeResult:
        result = VisionCascadeResult(
            profile=dict(analysis.profile),
            content_hash=content_hash,
            route=analysis.route,
            provider=analysis.provider,
            model=analysis.model,
            confidence=_confidence(analysis.profile),
            cache_hit=False,
            attempts=tuple(attempts),
            input_tokens=analysis.input_tokens,
            output_tokens=analysis.output_tokens,
            actual_cost_rub=analysis.actual_cost_rub,
            metadata=dict(metadata),
        )
        await self._repository.store(
            result,
            analysis_type=self.analysis_type,
            prompt_version=self.prompt_version,
            input_tokens=analysis.input_tokens,
            output_tokens=analysis.output_tokens,
            actual_cost_rub=analysis.actual_cost_rub,
        )
        return result

    def _cache_models(self, *, sensitive: bool) -> tuple[str, ...]:
        if sensitive:
            return (self._sensitive.model,) if self._sensitive is not None else ()
        return self.configured_models


def _cached_result(cached: CachedVisionAnalysis) -> VisionCascadeResult:
    return VisionCascadeResult(
        profile=dict(cached.profile),
        content_hash=cached.content_hash,
        route=cached.route,
        provider=cached.provider,
        model=cached.model,
        confidence=cached.confidence,
        cache_hit=True,
        attempts=(),
        input_tokens=cached.input_tokens,
        output_tokens=cached.output_tokens,
        actual_cost_rub=cached.actual_cost_rub,
        metadata={"cache_id": cached.cache_id},
    )


def _confidence(profile: Mapping[str, object]) -> int:
    try:
        return max(0, min(int(profile.get("confidence", 0) or 0), 100))
    except (TypeError, ValueError):
        return 0


def _is_refusal(error: BaseException) -> bool:
    text = str(error).casefold()
    return any(marker in text for marker in _REFUSAL_MARKERS)


__all__ = (
    "VisionCascadeRouter",
    "_confidence",
    "_is_refusal",
)
