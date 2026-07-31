from __future__ import annotations

import os
from decimal import Decimal

from velvet_bot.core.config import Settings
from velvet_bot.core.config.settings import (
    LOCAL_OPENAI_COMPATIBLE_PROVIDER,
    validate_local_vision_base_url,
)
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import (
    AIRequestExecutor,
    AITokenPricing,
    AIUsageService,
    load_token_pricing,
)
from velvet_bot.domains.vision_routing.cache import VisionAnalysisCacheRepository
from velvet_bot.domains.vision_routing.client import MeteredVisionClient
from velvet_bot.domains.vision_routing.models import VisionRoute, VisionRouteConfig
from velvet_bot.domains.vision_routing.service import VisionCascadeRouter


def build_vision_cascade_router(
    *,
    settings: Settings,
    database: Database,
    ai_usage_service: AIUsageService,
) -> VisionCascadeRouter:
    executor: AIRequestExecutor = AIRequestExecutor(ai_usage_service)
    flash_config = _route_config(
        settings=settings,
        route=VisionRoute.FLASH,
        default_model=settings.ai_vision_model,
    )
    flash = MeteredVisionClient(config=flash_config, executor=executor)

    pro_model = (
        os.getenv("AI_VISION_PRO_MODEL", "").strip()
        or settings.ai_vision_compare_model
        or ""
    )
    pro = (
        MeteredVisionClient(
            config=_route_config(
                settings=settings,
                route=VisionRoute.PRO,
                default_model=pro_model,
            ),
            executor=executor,
        )
        if pro_model
        else None
    )

    sensitive_model = (
        os.getenv("AI_VISION_SENSITIVE_MODEL", "").strip()
        or settings.ai_vision_fallback_model
        or ""
    )
    sensitive = (
        MeteredVisionClient(
            config=_route_config(
                settings=settings,
                route=VisionRoute.SENSITIVE,
                default_model=sensitive_model,
            ),
            executor=executor,
        )
        if sensitive_model
        else None
    )

    return VisionCascadeRouter(
        flash=flash,
        pro=pro,
        sensitive=sensitive,
        repository=VisionAnalysisCacheRepository(database),
        confidence_threshold=_bounded_int(
            os.getenv("AI_VISION_CASCADE_CONFIDENCE_THRESHOLD", "70"),
            default=70,
            minimum=1,
            maximum=100,
        ),
        prompt_version=_bounded_int(
            os.getenv("AI_VISION_PROMPT_VERSION", "1"),
            default=1,
            minimum=1,
            maximum=1_000_000,
        ),
        analysis_type="semantic-profile",
    )


def _route_config(
    *,
    settings: Settings,
    route: VisionRoute,
    default_model: str,
) -> VisionRouteConfig:
    prefix = f"AI_VISION_{route.value.upper()}"
    provider = (
        os.getenv(f"{prefix}_PROVIDER", "").strip().casefold()
        or settings.ai_vision_provider
    )
    base_url = (
        os.getenv(f"{prefix}_BASE_URL", "").strip().rstrip("/")
        or settings.ai_vision_base_url
    )
    validate_local_vision_base_url(
        provider,
        base_url,
        variable_name=f"{prefix}_BASE_URL",
    )
    model = os.getenv(f"{prefix}_MODEL", "").strip() or default_model.strip()
    api_key = (
        os.getenv(f"{prefix}_API_KEY", "").strip()
        or settings.ai_vision_api_key
        or None
    )
    pricing = (
        AITokenPricing(
            input_rub_per_million=Decimal("0"),
            output_rub_per_million=Decimal("0"),
        )
        if provider in {"ollama", LOCAL_OPENAI_COMPATIBLE_PROVIDER}
        else load_token_pricing(prefix)
    )
    return VisionRouteConfig(
        route=route,
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_seconds=_bounded_int(
            os.getenv(f"{prefix}_TIMEOUT_SECONDS", str(settings.ai_vision_timeout_seconds)),
            default=settings.ai_vision_timeout_seconds,
            minimum=10,
            maximum=900,
        ),
        max_attempts=_bounded_int(
            os.getenv(f"{prefix}_MAX_ATTEMPTS", str(settings.ai_vision_max_attempts)),
            default=settings.ai_vision_max_attempts,
            minimum=1,
            maximum=5,
        ),
        pricing=pricing,
    )


def _bounded_int(
    value: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value.strip())
    except (AttributeError, TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


__all__ = ("build_vision_cascade_router",)
