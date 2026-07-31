from __future__ import annotations

import asyncio
import hashlib
from typing import Mapping

from velvet_bot.ai_vision import VisionAnalysisError, _prepare_image
from velvet_bot.domains.vision_routing.cache import VisionAnalysisCacheRepository
from velvet_bot.domains.vision_routing.client import MeteredVisionClient
from velvet_bot.domains.vision_routing.models import (
    CachedVisionAnalysis,
    VisionAnalysisMode,
    VisionCascadeResult,
    VisionProviderAnalysis,
    VisionRoute,
)
from velvet_bot.domains.vision_routing.profile_contract import PROFILE_SCHEMA_VERSION

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
        adult_confirmed: bool = False,
        user_id: int | None = None,
        chat_id: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> VisionCascadeResult:
        mode = VisionAnalysisMode.SENSITIVE if sensitive else VisionAnalysisMode.STANDARD
        if mode is VisionAnalysisMode.SENSITIVE and not adult_confirmed:
            raise VisionAnalysisError(
                "Sensitive VL route требует явного adult_confirmed=true."
            )

        content_hash = hashlib.sha256(source).hexdigest()
        analysis_type = self._analysis_type(mode)
        cached = await self._repository.find(
            content_hash=content_hash,
            analysis_type=analysis_type,
            prompt_version=self.prompt_version,
            models=self._cache_models(mode=mode),
        )
        if cached is not None:
            return _cached_result(cached, mode=mode)

        prepared = await asyncio.to_thread(_prepare_image, source)
        common_metadata = {
            "content_hash": content_hash,
            "analysis_type": analysis_type,
            "analysis_mode": mode.value,
            "schema_version": PROFILE_SCHEMA_VERSION,
            "prompt_version": self.prompt_version,
            "adult_confirmed": adult_confirmed,
            **dict(metadata or {}),
        }
        attempts: list[VisionRoute] = []

        if mode is VisionAnalysisMode.SENSITIVE:
            if self._sensitive is None:
                raise VisionAnalysisError("Sensitive VL route не настроен.")
            analysis = await self._call(
                self._sensitive,
                prepared,
                analysis_type=analysis_type,
                attempts=attempts,
                user_id=user_id,
                chat_id=chat_id,
                metadata=common_metadata,
            )
            confidence = _confidence(analysis.profile)
            return await self._accept(
                analysis,
                content_hash=content_hash,
                analysis_type=analysis_type,
                attempts=attempts,
                metadata={
                    "analysis_mode": mode.value,
                    "adult_confirmed": True,
                    "manual_review_required": confidence < self.confidence_threshold,
                    "manual_review_reason": (
                        "low_sensitive_confidence"
                        if confidence < self.confidence_threshold
                        else None
                    ),
                },
            )

        flash_error: VisionAnalysisError | None = None
        flash_analysis: VisionProviderAnalysis | None = None
        try:
            flash_analysis = await self._call(
                self._flash,
                prepared,
                analysis_type=analysis_type,
                attempts=attempts,
                user_id=user_id,
                chat_id=chat_id,
                metadata=common_metadata,
            )
        except VisionAnalysisError as error:
            flash_error = error
            if self._pro is None:
                raise

        if flash_analysis is not None:
            confidence = _confidence(flash_analysis.profile)
            if confidence >= self.confidence_threshold or self._pro is None:
                return await self._accept(
                    flash_analysis,
                    content_hash=content_hash,
                    analysis_type=analysis_type,
                    attempts=attempts,
                    metadata={
                        "analysis_mode": mode.value,
                        "confidence_threshold": self.confidence_threshold,
                        "pro_required": False,
                    },
                )

        if self._pro is None:
            if flash_error is not None:
                raise flash_error
            raise VisionAnalysisError("Pro VL route не настроен.")

        fallback_reason = (
            "flash_refusal"
            if flash_error is not None and _is_refusal(flash_error)
            else "flash_error"
            if flash_error is not None
            else "low_confidence"
        )
        try:
            pro_analysis = await self._call(
                self._pro,
                prepared,
                analysis_type=analysis_type,
                attempts=attempts,
                user_id=user_id,
                chat_id=chat_id,
                metadata={
                    **common_metadata,
                    "fallback_reason": fallback_reason,
                    "flash_confidence": (
                        _confidence(flash_analysis.profile)
                        if flash_analysis is not None
                        else None
                    ),
                },
            )
        except VisionAnalysisError as error:
            if flash_analysis is not None:
                return await self._accept(
                    flash_analysis,
                    content_hash=content_hash,
                    analysis_type=analysis_type,
                    attempts=attempts,
                    metadata={
                        "analysis_mode": mode.value,
                        "fallback_reason": "pro_error_use_flash",
                        "pro_error": str(error)[:500],
                    },
                )
            raise

        return await self._accept(
            pro_analysis,
            content_hash=content_hash,
            analysis_type=analysis_type,
            attempts=attempts,
            metadata={
                "analysis_mode": mode.value,
                "fallback_reason": fallback_reason,
                "confidence_threshold": self.confidence_threshold,
            },
        )

    async def _call(
        self,
        client: MeteredVisionClient,
        prepared: bytes,
        *,
        analysis_type: str,
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
            operation=f"vision.{analysis_type}.{client.route.value}",
            metadata=metadata,
        )

    async def _accept(
        self,
        analysis: VisionProviderAnalysis,
        *,
        content_hash: str,
        analysis_type: str,
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
            analysis_type=analysis_type,
            prompt_version=self.prompt_version,
            input_tokens=analysis.input_tokens,
            output_tokens=analysis.output_tokens,
            actual_cost_rub=analysis.actual_cost_rub,
        )
        return result

    def _analysis_type(self, mode: VisionAnalysisMode) -> str:
        return f"{self.analysis_type}:schema-{PROFILE_SCHEMA_VERSION}:{mode.value}"

    def _cache_models(self, *, mode: VisionAnalysisMode) -> tuple[str, ...]:
        if mode is VisionAnalysisMode.SENSITIVE:
            return (self._sensitive.model,) if self._sensitive is not None else ()
        clients = (self._flash, self._pro)
        return tuple(
            dict.fromkeys(client.model for client in clients if client is not None)
        )


def _cached_result(
    cached: CachedVisionAnalysis,
    *,
    mode: VisionAnalysisMode,
) -> VisionCascadeResult:
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
        metadata={"cache_id": cached.cache_id, "analysis_mode": mode.value},
    )


def _confidence(profile: Mapping[str, object]) -> int:
    try:
        return max(0, min(int(profile.get("confidence", 0) or 0), 100))
    except (TypeError, ValueError):
        return 0


def _is_refusal(error: BaseException) -> bool:
    text = str(error).casefold()
    return any(marker in text for marker in _REFUSAL_MARKERS)


__all__ = ("VisionCascadeRouter", "_confidence", "_is_refusal")
