from __future__ import annotations

import os
from decimal import Decimal
from urllib.parse import urlsplit

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
from velvet_bot.domains.vision_routing.models import (
    VisionAnalysisContract,
    VisionAnalysisMode,
    VisionRoute,
    VisionRouteConfig,
)
from velvet_bot.domains.vision_routing.profile_contract import PROFILE_SCHEMA_VERSION
from velvet_bot.domains.vision_routing.service import VisionCascadeRouter


def build_vision_cascade_router(
    *,
    settings: Settings,
    database: Database,
    ai_usage_service: AIUsageService,
    contract: VisionAnalysisContract | None = None,
    analysis_type: str = "semantic-profile",
    prompt_version: int | None = None,
    include_sensitive: bool = True,
    include_pro: bool = True,
) -> VisionCascadeRouter:
    executor: AIRequestExecutor = AIRequestExecutor(ai_usage_service)
    resolved_prompt_version = (
        max(1, int(prompt_version))
        if prompt_version is not None
        else _bounded_int(
            os.getenv("AI_VISION_PROMPT_VERSION", "1"),
            default=1,
            minimum=1,
            maximum=1_000_000,
        )
    )
    schema_version = (
        contract.schema_version if contract is not None else PROFILE_SCHEMA_VERSION
    )
    flash_config = _route_config(
        settings=settings,
        route=VisionRoute.FLASH,
        default_model=settings.ai_vision_model,
        prompt_version=resolved_prompt_version,
        schema_version=schema_version,
    )
    flash = MeteredVisionClient(
        config=flash_config,
        executor=executor,
        contract=contract,
    )
    main_sensitive = (
        MeteredVisionClient(
            config=flash_config,
            executor=executor,
            contract=contract,
            analysis_mode=VisionAnalysisMode.SENSITIVE,
        )
        if include_sensitive
        else None
    )

    pro: MeteredVisionClient | None = None
    if include_pro and _env_flag("AI_VISION_CLOUD_PRO_ENABLED", default=False):
        pro_model = os.getenv("AI_VISION_PRO_MODEL", "").strip()
        if not pro_model:
            raise RuntimeError(
                "AI_VISION_CLOUD_PRO_ENABLED=true требует AI_VISION_PRO_MODEL."
            )
        pro_config = _route_config(
            settings=settings,
            route=VisionRoute.PRO,
            default_model=pro_model,
            prompt_version=resolved_prompt_version,
            schema_version=schema_version,
        )
        _validate_cloud_pro_provider(pro_config)
        pro = MeteredVisionClient(
            config=pro_config,
            executor=executor,
            contract=contract,
        )

    sensitive: MeteredVisionClient | None = None
    uncensored_enabled = include_sensitive and _env_flag(
        "AI_VISION_LOCAL_UNCENSORED_ENABLED",
        default=False,
    )
    if uncensored_enabled:
        sensitive_model = os.getenv("AI_VISION_SENSITIVE_MODEL", "").strip()
        if not sensitive_model:
            raise RuntimeError(
                "AI_VISION_LOCAL_UNCENSORED_ENABLED=true требует "
                "AI_VISION_SENSITIVE_MODEL."
            )
        if sensitive_model == flash.model:
            raise RuntimeError(
                "LOCAL_UNCENSORED должен быть отдельной моделью, а не alias LOCAL_MAIN."
            )
        sensitive_config = _route_config(
            settings=settings,
            route=VisionRoute.SENSITIVE,
            default_model=sensitive_model,
            prompt_version=resolved_prompt_version,
            schema_version=schema_version,
        )
        _validate_sensitive_provider(sensitive_config)
        sensitive = MeteredVisionClient(
            config=sensitive_config,
            executor=executor,
            contract=contract,
        )

    return VisionCascadeRouter(
        flash=flash,
        main_sensitive=main_sensitive,
        pro=pro,
        sensitive=sensitive,
        repository=VisionAnalysisCacheRepository(database),
        confidence_threshold=_bounded_int(
            os.getenv("AI_VISION_CASCADE_CONFIDENCE_THRESHOLD", "70"),
            default=70,
            minimum=1,
            maximum=100,
        ),
        prompt_version=resolved_prompt_version,
        analysis_type=analysis_type,
        schema_version=schema_version,
    )


def _route_config(
    *,
    settings: Settings,
    route: VisionRoute,
    default_model: str,
    prompt_version: int = 1,
    schema_version: int = PROFILE_SCHEMA_VERSION,
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
    if (
        provider == "openai_compatible"
        and urlsplit(base_url).hostname == "vision-gateway"
    ):
        provider = LOCAL_OPENAI_COMPATIBLE_PROVIDER
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
        prompt_version=prompt_version,
        schema_version=schema_version,
    )


def _validate_cloud_pro_provider(config: VisionRouteConfig) -> None:
    if config.provider == "openai_compatible":
        return
    raise RuntimeError(
        "CLOUD_PRO должен использовать отдельный openai_compatible cloud endpoint."
    )


def _validate_sensitive_provider(config: VisionRouteConfig) -> None:
    if config.provider in {"ollama", LOCAL_OPENAI_COMPATIBLE_PROVIDER}:
        return
    raise RuntimeError(
        "LOCAL_UNCENSORED должен оставаться локальным; cloud sensitive VL запрещён."
    )


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.getenv(name, "").strip().casefold()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} должен быть true/false, yes/no, on/off или 1/0.")


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


__all__ = (
    "build_vision_cascade_router",
    "_env_flag",
    "_route_config",
    "_validate_cloud_pro_provider",
    "_validate_sensitive_provider",
)
