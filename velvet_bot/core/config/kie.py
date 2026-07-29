from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv

from velvet_bot.core.config.settings import parse_boolean, parse_bounded_integer
from velvet_bot.domains.media_generation import (
    KieInputMode,
    KieModelAlias,
    KieModelCatalog,
    KiePricing,
)


@dataclass(frozen=True, slots=True)
class KieSettings:
    enabled: bool
    api_key: str | None
    base_url: str
    file_upload_base_url: str
    timeout_seconds: int
    poll_interval_seconds: int
    task_timeout_seconds: int
    usd_to_rub: Decimal
    models: KieModelCatalog
    pricing: KiePricing


def load_kie_settings() -> KieSettings:
    load_dotenv()
    enabled = parse_boolean(
        os.getenv("KIE_ENABLED", "false"),
        variable_name="KIE_ENABLED",
    )
    api_key = os.getenv("KIE_API_KEY", "").strip() or None
    base_url = (
        os.getenv("KIE_BASE_URL", "https://api.kie.ai/api/v1")
        .strip()
        .rstrip("/")
    )
    file_upload_base_url = (
        os.getenv("KIE_FILE_UPLOAD_BASE_URL", "https://kieai.redpandaai.co")
        .strip()
        .rstrip("/")
    )
    if not base_url:
        raise RuntimeError("KIE_BASE_URL не может быть пустым.")
    if not file_upload_base_url:
        raise RuntimeError("KIE_FILE_UPLOAD_BASE_URL не может быть пустым.")

    legacy_seedream = os.getenv("KIE_SEEDREAM_5_PRO_MODEL", "").strip()
    legacy_grok_video = os.getenv("KIE_GROK_IMAGINE_VIDEO_MODEL", "").strip()
    grok_image_to_video = os.getenv(
        "KIE_GROK_IMAGINE_IMAGE_TO_VIDEO_MODEL",
        legacy_grok_video or "grok-imagine/image-to-video",
    ).strip()
    models = KieModelCatalog(
        seedream_5_pro=legacy_seedream,
        seedream_5_pro_text=os.getenv(
            "KIE_SEEDREAM_5_PRO_TEXT_MODEL",
            "seedream/5-pro-text-to-image",
        ).strip(),
        seedream_5_pro_image=os.getenv(
            "KIE_SEEDREAM_5_PRO_IMAGE_MODEL",
            legacy_seedream or "seedream/5-pro-image-to-image",
        ).strip(),
        nano_banana_pro=(
            os.getenv("KIE_NANO_BANANA_PRO_MODEL", "nano-banana-pro").strip()
        ),
        grok_imagine_video=grok_image_to_video,
    )
    usd_to_rub = _parse_non_negative_decimal(
        os.getenv("KIE_USD_TO_RUB", "0"),
        variable_name="KIE_USD_TO_RUB",
    )
    if enabled and not api_key:
        raise RuntimeError("KIE_ENABLED=true требует непустой KIE_API_KEY.")
    if enabled and usd_to_rub <= 0:
        raise RuntimeError("KIE_ENABLED=true требует KIE_USD_TO_RUB больше нуля.")
    if enabled:
        required_routes = (
            (KieModelAlias.NANO_BANANA_PRO, KieInputMode.TEXT),
            (KieModelAlias.SEEDREAM_5_PRO, KieInputMode.TEXT),
            (KieModelAlias.SEEDREAM_5_PRO, KieInputMode.PHOTO_TEXT),
            (KieModelAlias.GROK_IMAGINE_VIDEO, KieInputMode.PHOTO_TEXT),
        )
        try:
            for alias, input_mode in required_routes:
                models.provider_model(alias, input_mode=input_mode)
        except ValueError as error:
            raise RuntimeError(
                "KIE_ENABLED=true требует model id для Nano Banana Pro, "
                "обоих режимов Seedream 5 Pro и Grok Imagine image-to-video."
            ) from error

    pricing = KiePricing(
        seedream_basic_usd=_parse_non_negative_decimal(
            os.getenv("KIE_SEEDREAM_BASIC_USD", "0.075"),
            variable_name="KIE_SEEDREAM_BASIC_USD",
        ),
        seedream_high_usd=_parse_non_negative_decimal(
            os.getenv("KIE_SEEDREAM_HIGH_USD", "0.15"),
            variable_name="KIE_SEEDREAM_HIGH_USD",
        ),
        nano_1k_2k_usd=_parse_non_negative_decimal(
            os.getenv("KIE_NANO_1K_2K_USD", "0.09"),
            variable_name="KIE_NANO_1K_2K_USD",
        ),
        nano_4k_usd=_parse_non_negative_decimal(
            os.getenv("KIE_NANO_4K_USD", "0.12"),
            variable_name="KIE_NANO_4K_USD",
        ),
        grok_480p_usd_per_second=_parse_non_negative_decimal(
            os.getenv("KIE_GROK_480P_USD_PER_SECOND", "0.008"),
            variable_name="KIE_GROK_480P_USD_PER_SECOND",
        ),
        grok_720p_usd_per_second=_parse_non_negative_decimal(
            os.getenv("KIE_GROK_720P_USD_PER_SECOND", "0.015"),
            variable_name="KIE_GROK_720P_USD_PER_SECOND",
        ),
    )
    return KieSettings(
        enabled=enabled,
        api_key=api_key,
        base_url=base_url,
        file_upload_base_url=file_upload_base_url,
        timeout_seconds=parse_bounded_integer(
            os.getenv("KIE_TIMEOUT_SECONDS", "60"),
            variable_name="KIE_TIMEOUT_SECONDS",
            default=60,
            minimum=5,
            maximum=300,
        ),
        poll_interval_seconds=parse_bounded_integer(
            os.getenv("KIE_POLL_INTERVAL_SECONDS", "4"),
            variable_name="KIE_POLL_INTERVAL_SECONDS",
            default=4,
            minimum=1,
            maximum=60,
        ),
        task_timeout_seconds=parse_bounded_integer(
            os.getenv("KIE_TASK_TIMEOUT_SECONDS", "900"),
            variable_name="KIE_TASK_TIMEOUT_SECONDS",
            default=900,
            minimum=60,
            maximum=3600,
        ),
        usd_to_rub=usd_to_rub,
        models=models,
        pricing=pricing,
    )


def _parse_non_negative_decimal(value: str, *, variable_name: str) -> Decimal:
    try:
        result = Decimal(value.strip())
    except (InvalidOperation, ValueError) as error:
        raise RuntimeError(f"{variable_name} должен быть десятичным числом.") from error
    if not result.is_finite() or result < 0:
        raise RuntimeError(f"{variable_name} не может быть отрицательным.")
    return result


__all__ = ("KieSettings", "load_kie_settings")
