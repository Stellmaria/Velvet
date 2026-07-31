from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Mapping

from velvet_bot.core.config.settings import LOCAL_OPENAI_COMPATIBLE_PROVIDER
from velvet_bot.domains.ai_usage import AITokenPricing


class VisionRoute(StrEnum):
    FLASH = "flash"
    PRO = "pro"
    SENSITIVE = "sensitive"


@dataclass(frozen=True, slots=True)
class VisionRouteConfig:
    route: VisionRoute
    provider: str
    base_url: str
    model: str
    api_key: str | None
    timeout_seconds: int
    max_attempts: int
    pricing: AITokenPricing

    def __post_init__(self) -> None:
        provider = self.provider.strip().casefold()
        supported = {
            "ollama",
            "openai_compatible",
            LOCAL_OPENAI_COMPATIBLE_PROVIDER,
        }
        if provider not in supported:
            raise ValueError(
                "VL provider должен быть ollama, openai_compatible или "
                "local_openai_compatible."
            )
        if not self.base_url.strip():
            raise ValueError("VL base URL не может быть пустым.")
        if not self.model.strip():
            raise ValueError("VL model не может быть пустой.")
        if provider == "openai_compatible" and not (self.api_key or "").strip():
            raise ValueError("Облачный VL provider требует API key.")
        if self.timeout_seconds < 10:
            raise ValueError("VL timeout должен быть не меньше 10 секунд.")
        if self.max_attempts < 1:
            raise ValueError("VL max_attempts должен быть положительным.")


@dataclass(frozen=True, slots=True)
class VisionProviderAnalysis:
    profile: Mapping[str, object]
    provider: str
    model: str
    route: VisionRoute
    input_tokens: int
    output_tokens: int
    usage_reported: bool
    actual_cost_rub: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class CachedVisionAnalysis:
    cache_id: int
    content_hash: str
    analysis_type: str
    prompt_version: int
    route: VisionRoute
    provider: str
    model: str
    profile: Mapping[str, object]
    confidence: int
    input_tokens: int = 0
    output_tokens: int = 0
    actual_cost_rub: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class VisionCascadeResult:
    profile: Mapping[str, object]
    content_hash: str
    route: VisionRoute
    provider: str
    model: str
    confidence: int
    cache_hit: bool
    attempts: tuple[VisionRoute, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0
    actual_cost_rub: Decimal = Decimal("0")
    metadata: Mapping[str, object] = field(default_factory=dict)


__all__ = (
    "CachedVisionAnalysis",
    "VisionCascadeResult",
    "VisionProviderAnalysis",
    "VisionRoute",
    "VisionRouteConfig",
)
