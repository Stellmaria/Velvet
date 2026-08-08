from __future__ import annotations

import asyncio
import hashlib
from typing import Mapping

from velvet_bot.ai_vision import VisionAnalysisError, _prepare_image
from velvet_bot.domains.vision_routing.cache import VisionAnalysisCacheRepository
from velvet_bot.domains.vision_routing.client import MeteredVisionClient
from velvet_bot.domains.vision_routing.failures import VisionRefusalError
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
        main_sensitive: MeteredVisionClient | None = None,
        confidence_threshold: int = 70,
        prompt_version: int = 1,
        analysis_type: str = "semantic-profile",
        schema_version: int = PROFILE_SCHEMA_VERSION,
    ) -> None:
        self._flash = flash
        self._pro = pro
        self._sensitive = sensitive
        self._main_sensitive = main_sensitive
        if main_sensitive is not None and main_sensitive.model != flash.model:
            raise ValueError(
                "Sensitive LOCAL_MAIN client должен использовать ту же модель, что и standard LOCAL_MAIN."
            )
        self._repository = repository
        self.confidence_threshold = max(1, min(int(confidence_threshold), 100))
        self.prompt_version = max(1, int(prompt_version))
        self.analysis_type = analysis_type.strip()
        self.schema_version = max(1, int(schema_version))
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
        clients = (self._flash, self._main_sensitive, self._pro, self._sensitive)
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
        force_pro: bool = False,
        force_uncensored: bool = False,
        user_id: int | None = None,
        chat_id: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> VisionCascadeResult:
        mode = VisionAnalysisMode.SENSITIVE if sensitive else VisionAnalysisMode.STANDARD
        self._validate_route_request(
            mode=mode,
            adult_confirmed=adult_confirmed,
            force_pro=force_pro,
            force_uncensored=force_uncensored,
        )

        content_hash = hashlib.sha256(source).hexdigest()
        analysis_type = self._analysis_type(
            mode,
            force_pro=force_pro,
            force_uncensored=force_uncensored,
        )
        cached = await self._repository.find(
            content_hash=content_hash,
            analysis_type=analysis_type,
            prompt_version=self.prompt_version,
            models=self._cache_models(
                mode=mode,
                force_pro=force_pro,
                force_uncensored=force_uncensored,
            ),
        )
        if cached is not None:
            return _cached_result(
                cached,
                mode=mode,
                prompt_version=self.prompt_version,
                schema_version=self.schema_version,
            )

        prepared = await asyncio.to_thread(_prepare_image, source)
        common_metadata = {
            **dict(metadata or {}),
            "content_hash": content_hash,
            "analysis_type": analysis_type,
            "analysis_mode": mode.value,
            "schema_version": self.schema_version,
            "prompt_version": self.prompt_version,
            "adult_confirmed": mode is VisionAnalysisMode.SENSITIVE,
            "force_pro": force_pro,
            "force_uncensored": force_uncensored,
        }
        attempts: list[VisionRoute] = []

        if mode is VisionAnalysisMode.SENSITIVE:
            return await self._analyze_sensitive(
                prepared,
                content_hash=content_hash,
                analysis_type=analysis_type,
                attempts=attempts,
                common_metadata=common_metadata,
                force_uncensored=force_uncensored,
                user_id=user_id,
                chat_id=chat_id,
            )

        return await self._analyze_standard(
            prepared,
            content_hash=content_hash,
            analysis_type=analysis_type,
            attempts=attempts,
            common_metadata=common_metadata,
            force_pro=force_pro,
            user_id=user_id,
            chat_id=chat_id,
        )

    async def _analyze_standard(
        self,
        prepared: bytes,
        *,
        content_hash: str,
        analysis_type: str,
        attempts: list[VisionRoute],
        common_metadata: Mapping[str, object],
        force_pro: bool,
        user_id: int | None,
        chat_id: int | None,
    ) -> VisionCascadeResult:
        main_error: VisionAnalysisError | None = None
        main_analysis: VisionProviderAnalysis | None = None
        try:
            main_analysis = await self._call(
                self._flash,
                prepared,
                analysis_type=analysis_type,
                attempts=attempts,
                user_id=user_id,
                chat_id=chat_id,
                metadata=common_metadata,
            )
        except VisionAnalysisError as error:
            main_error = error
            if self._pro is None:
                raise

        if main_analysis is not None:
            confidence = _confidence(main_analysis.profile)
            if (
                not force_pro
                and (confidence >= self.confidence_threshold or self._pro is None)
            ):
                return await self._accept(
                    main_analysis,
                    content_hash=content_hash,
                    analysis_type=analysis_type,
                    attempts=attempts,
                    metadata={
                        "analysis_mode": VisionAnalysisMode.STANDARD.value,
                        "schema_version": self.schema_version,
                        "prompt_version": self.prompt_version,
                        "confidence_threshold": self.confidence_threshold,
                        "pro_required": False,
                    },
                )

        if self._pro is None:
            if main_error is not None:
                raise main_error
            raise VisionAnalysisError("CLOUD_PRO VL route выключен или не настроен.")

        fallback_reason = (
            "owner_force_pro"
            if force_pro
            else "main_refusal"
            if main_error is not None and _is_refusal(main_error)
            else "main_error"
            if main_error is not None
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
                    **dict(common_metadata),
                    "fallback_reason": fallback_reason,
                    "main_confidence": (
                        _confidence(main_analysis.profile)
                        if main_analysis is not None
                        else None
                    ),
                },
            )
        except VisionAnalysisError as error:
            if main_analysis is not None:
                return await self._accept(
                    main_analysis,
                    content_hash=content_hash,
                    analysis_type=analysis_type,
                    attempts=attempts,
                    metadata={
                        "analysis_mode": VisionAnalysisMode.STANDARD.value,
                        "schema_version": self.schema_version,
                        "prompt_version": self.prompt_version,
                        "fallback_reason": "pro_error_use_main",
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
                "analysis_mode": VisionAnalysisMode.STANDARD.value,
                "schema_version": self.schema_version,
                "prompt_version": self.prompt_version,
                "fallback_reason": fallback_reason,
                "confidence_threshold": self.confidence_threshold,
            },
        )

    async def _analyze_sensitive(
        self,
        prepared: bytes,
        *,
        content_hash: str,
        analysis_type: str,
        attempts: list[VisionRoute],
        common_metadata: Mapping[str, object],
        force_uncensored: bool,
        user_id: int | None,
        chat_id: int | None,
    ) -> VisionCascadeResult:
        main_client = self._main_sensitive or self._flash
        main_error: VisionAnalysisError | None = None
        main_analysis: VisionProviderAnalysis | None = None
        try:
            main_analysis = await self._call(
                main_client,
                prepared,
                analysis_type=analysis_type,
                attempts=attempts,
                user_id=user_id,
                chat_id=chat_id,
                metadata=common_metadata,
            )
        except VisionAnalysisError as error:
            main_error = error
            if self._sensitive is None:
                raise

        if main_analysis is not None:
            confidence = _confidence(main_analysis.profile)
            if (
                not force_uncensored
                and (confidence >= self.confidence_threshold or self._sensitive is None)
            ):
                return await self._accept(
                    main_analysis,
                    content_hash=content_hash,
                    analysis_type=analysis_type,
                    attempts=attempts,
                    metadata={
                        "analysis_mode": VisionAnalysisMode.SENSITIVE.value,
                        "schema_version": self.schema_version,
                        "prompt_version": self.prompt_version,
                        "adult_confirmed": True,
                        "uncensored_required": False,
                        "manual_review_required": confidence < self.confidence_threshold,
                        "manual_review_reason": (
                            "low_sensitive_confidence"
                            if confidence < self.confidence_threshold
                            else None
                        ),
                    },
                )

        if self._sensitive is None:
            if main_error is not None:
                raise main_error
            raise VisionAnalysisError(
                "LOCAL_UNCENSORED VL route выключен или не настроен."
            )

        fallback_reason = (
            "owner_force_uncensored"
            if force_uncensored
            else "main_refusal"
            if main_error is not None and _is_refusal(main_error)
            else "main_error"
            if main_error is not None
            else "low_sensitive_confidence"
        )
        try:
            uncensored_analysis = await self._call(
                self._sensitive,
                prepared,
                analysis_type=analysis_type,
                attempts=attempts,
                user_id=user_id,
                chat_id=chat_id,
                metadata={
                    **dict(common_metadata),
                    "fallback_reason": fallback_reason,
                    "main_confidence": (
                        _confidence(main_analysis.profile)
                        if main_analysis is not None
                        else None
                    ),
                },
            )
        except VisionAnalysisError as error:
            if main_analysis is not None:
                return await self._accept(
                    main_analysis,
                    content_hash=content_hash,
                    analysis_type=analysis_type,
                    attempts=attempts,
                    metadata={
                        "analysis_mode": VisionAnalysisMode.SENSITIVE.value,
                        "schema_version": self.schema_version,
                        "prompt_version": self.prompt_version,
                        "adult_confirmed": True,
                        "fallback_reason": "uncensored_error_use_main",
                        "uncensored_error": str(error)[:500],
                        "manual_review_required": True,
                        "manual_review_reason": "uncensored_fallback_failed",
                    },
                )
            raise

        confidence = _confidence(uncensored_analysis.profile)
        return await self._accept(
            uncensored_analysis,
            content_hash=content_hash,
            analysis_type=analysis_type,
            attempts=attempts,
            metadata={
                "analysis_mode": VisionAnalysisMode.SENSITIVE.value,
                "schema_version": self.schema_version,
                "prompt_version": self.prompt_version,
                "adult_confirmed": True,
                "fallback_reason": fallback_reason,
                "confidence_threshold": self.confidence_threshold,
                "manual_review_required": confidence < self.confidence_threshold,
                "manual_review_reason": (
                    "low_uncensored_confidence"
                    if confidence < self.confidence_threshold
                    else None
                ),
            },
        )

    def _validate_route_request(
        self,
        *,
        mode: VisionAnalysisMode,
        adult_confirmed: bool,
        force_pro: bool,
        force_uncensored: bool,
    ) -> None:
        if mode is VisionAnalysisMode.SENSITIVE and not adult_confirmed:
            raise VisionAnalysisError(
                "Sensitive VL route требует явного adult_confirmed=true."
            )
        if mode is VisionAnalysisMode.SENSITIVE and force_pro:
            raise VisionAnalysisError("Sensitive VL никогда не отправляется в CLOUD_PRO.")
        if mode is VisionAnalysisMode.STANDARD and force_uncensored:
            raise VisionAnalysisError(
                "LOCAL_UNCENSORED доступен только для adult-confirmed sensitive route."
            )
        if force_pro and self._pro is None:
            raise VisionAnalysisError("CLOUD_PRO VL route выключен или не настроен.")
        if force_uncensored and self._sensitive is None:
            raise VisionAnalysisError(
                "LOCAL_UNCENSORED VL route выключен или не настроен."
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

    def _analysis_type(
        self,
        mode: VisionAnalysisMode,
        *,
        force_pro: bool = False,
        force_uncensored: bool = False,
    ) -> str:
        suffix = (
            ":force-pro"
            if force_pro
            else ":force-uncensored"
            if force_uncensored
            else ""
        )
        return (
            f"{self.analysis_type}:schema-{self.schema_version}:{mode.value}{suffix}"
        )

    def _cache_models(
        self,
        *,
        mode: VisionAnalysisMode,
        force_pro: bool = False,
        force_uncensored: bool = False,
    ) -> tuple[str, ...]:
        if force_pro:
            return (self._pro.model,) if self._pro is not None else ()
        if force_uncensored:
            return (self._sensitive.model,) if self._sensitive is not None else ()
        if mode is VisionAnalysisMode.SENSITIVE:
            clients = (self._main_sensitive or self._flash, self._sensitive)
        else:
            clients = (self._flash, self._pro)
        return tuple(
            dict.fromkeys(client.model for client in clients if client is not None)
        )


def _cached_result(
    cached: CachedVisionAnalysis,
    *,
    mode: VisionAnalysisMode,
    prompt_version: int,
    schema_version: int,
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
        metadata={
            "cache_id": cached.cache_id,
            "analysis_mode": mode.value,
            "schema_version": schema_version,
            "prompt_version": prompt_version,
        },
    )


def _confidence(profile: Mapping[str, object]) -> int:
    try:
        return max(0, min(int(profile.get("confidence", 0) or 0), 100))
    except (TypeError, ValueError):
        return 0


def _is_refusal(error: BaseException) -> bool:
    if isinstance(error, VisionRefusalError):
        return True
    text = str(error).casefold()
    return any(marker in text for marker in _REFUSAL_MARKERS)


__all__ = ("VisionCascadeRouter", "_confidence", "_is_refusal")
