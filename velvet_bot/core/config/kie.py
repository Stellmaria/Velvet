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
    grs_api_key: str | None = None
    grs_base_url: str = "https://grsaiapi.com"
    credit_usd: Decimal = Decimal("0.005")
    credit_byn: Decimal = Decimal("0.019")
    max_concurrent_generations: int = 4
    generation_max_attempts: int = 50


def load_kie_settings() -> KieSettings:
    load_dotenv()
    enabled = parse_boolean(
        os.getenv("KIE_ENABLED", "false"),
        variable_name="KIE_ENABLED",
    )
    api_key = os.getenv("KIE_API_KEY", "").strip() or None
    grs_api_key = os.getenv("GRS_API_KEY", "").strip() or None
    base_url = os.getenv("KIE_BASE_URL", "https://api.kie.ai/api/v1").strip().rstrip("/")
    file_upload_base_url = (
        os.getenv("KIE_FILE_UPLOAD_BASE_URL", "https://kieai.redpandaai.co")
        .strip()
        .rstrip("/")
    )
    grs_base_url = os.getenv("GRS_BASE_URL", "https://grsaiapi.com").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("KIE_BASE_URL не может быть пустым.")
    if not file_upload_base_url:
        raise RuntimeError("KIE_FILE_UPLOAD_BASE_URL не может быть пустым.")
    if not grs_base_url:
        raise RuntimeError("GRS_BASE_URL не может быть пустым.")

    legacy_seedream = os.getenv("KIE_SEEDREAM_5_PRO_MODEL", "").strip()
    legacy_grok_video = os.getenv("KIE_GROK_IMAGINE_VIDEO_MODEL", "").strip()
    legacy_grok_image_to_video = (
        legacy_grok_video if "image-to-video" in legacy_grok_video.casefold() else ""
    )
    grok_image_to_video = (
        os.getenv("KIE_GROK_IMAGINE_IMAGE_TO_VIDEO_MODEL", "").strip()
        or legacy_grok_image_to_video
        or "grok-imagine/image-to-video"
    )
    grok_15_image_to_video = (
        os.getenv("KIE_GROK_IMAGINE_VIDEO_15_MODEL", "").strip()
        or "grok-imagine-video-1-5-preview"
    )
    seedance_image_to_video = (
        os.getenv("KIE_SEEDANCE_15_PRO_MODEL", "").strip()
        or "bytedance/seedance-1.5-pro"
    )
    # Prefer the new explicit name. Keep the old variable only as a deployment bridge.
    wan_image_to_video = (
        os.getenv("KIE_WAN_27_IMAGE_TO_VIDEO_MODEL", "").strip()
        or os.getenv("KIE_WAN_26_IMAGE_TO_VIDEO_MODEL", "").strip()
        or "wan/2-7-image-to-video"
    )
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
        nano_banana_2=os.getenv(
            "GRS_NANO_BANANA_2_MODEL",
            "nano-banana-2",
        ).strip(),
        nano_banana_pro=os.getenv(
            "GRS_NANO_BANANA_PRO_MODEL",
            "nano-banana-pro",
        ).strip(),
        qwen2_image_edit=os.getenv(
            "KIE_QWEN2_IMAGE_EDIT_MODEL",
            "qwen2/image-edit",
        ).strip(),
        wan_27_image=os.getenv(
            "KIE_WAN_27_IMAGE_MODEL",
            "wan/2-7-image",
        ).strip(),
        flux_2_pro_image=os.getenv(
            "KIE_FLUX_2_PRO_IMAGE_MODEL",
            "flux-2/pro-image-to-image",
        ).strip(),
        grok_imagine_video=grok_image_to_video,
        grok_imagine_video_15=grok_15_image_to_video,
        seedance_15_pro_video=seedance_image_to_video,
        # Field name stays stable so already queued tasks remain readable.
        wan_26_image_to_video=wan_image_to_video,
    )
    usd_to_rub = _parse_non_negative_decimal(
        os.getenv("KIE_USD_TO_RUB", "").strip() or "0",
        variable_name="KIE_USD_TO_RUB",
    )
    credit_usd = _parse_non_negative_decimal(
        os.getenv("KIE_CREDIT_USD", "").strip() or "0.005",
        variable_name="KIE_CREDIT_USD",
    )
    credit_byn = _parse_non_negative_decimal(
        os.getenv("KIE_CREDIT_BYN", "").strip() or "0.019",
        variable_name="KIE_CREDIT_BYN",
    )
    if credit_usd <= 0:
        raise RuntimeError("KIE_CREDIT_USD должен быть больше нуля.")
    if credit_byn <= 0:
        raise RuntimeError("KIE_CREDIT_BYN должен быть больше нуля.")
    if enabled and not api_key:
        raise RuntimeError("KIE_ENABLED=true требует непустой KIE_API_KEY.")
    if enabled and not grs_api_key:
        raise RuntimeError(
            "KIE_ENABLED=true требует непустой GRS_API_KEY для Nano Banana 2/Pro."
        )
    if enabled and usd_to_rub <= 0:
        raise RuntimeError("KIE_ENABLED=true требует KIE_USD_TO_RUB больше нуля.")
    if enabled:
        required_routes = (
            (KieModelAlias.NANO_BANANA_2, KieInputMode.PHOTO_TEXT),
            (KieModelAlias.NANO_BANANA_PRO, KieInputMode.PHOTO_TEXT),
            (KieModelAlias.SEEDREAM_5_PRO, KieInputMode.TEXT),
            (KieModelAlias.SEEDREAM_5_PRO, KieInputMode.PHOTO_TEXT),
            (KieModelAlias.QWEN2_IMAGE_EDIT, KieInputMode.PHOTO_TEXT),
            (KieModelAlias.WAN_27_IMAGE, KieInputMode.PHOTO_TEXT),
            (KieModelAlias.FLUX_2_PRO_IMAGE, KieInputMode.PHOTO_TEXT),
            (KieModelAlias.GROK_IMAGINE_VIDEO, KieInputMode.PHOTO_TEXT),
            (KieModelAlias.GROK_IMAGINE_VIDEO_15, KieInputMode.PHOTO_TEXT),
            (KieModelAlias.SEEDANCE_15_PRO_VIDEO, KieInputMode.PHOTO_TEXT),
            (KieModelAlias.WAN_26_IMAGE_TO_VIDEO, KieInputMode.PHOTO_TEXT),
        )
        try:
            for alias, input_mode in required_routes:
                models.provider_model(alias, input_mode=input_mode)
        except ValueError as error:
            raise RuntimeError(
                "KIE_ENABLED=true требует model id Kie.ai для Seedream 5 Pro, "
                "Qwen Image 2.0, Wan 2.7 Image, FLUX.2 Pro и video-моделей, "
                "а также GRS model id для Nano Banana 2/Pro."
            ) from error

    pricing = KiePricing(
        seedream_basic_usd=_env_decimal("KIE_SEEDREAM_BASIC_USD", "0.075"),
        seedream_high_usd=_env_decimal("KIE_SEEDREAM_HIGH_USD", "0.15"),
        nano_banana_2_usd=_env_decimal("GRS_NANO_BANANA_2_USD", "0.02"),
        nano_banana_pro_usd=_env_decimal("GRS_NANO_BANANA_PRO_USD", "0.03"),
        qwen2_image_edit_usd=_env_decimal("KIE_QWEN2_IMAGE_EDIT_USD", "0.02"),
        wan_27_1k_usd=_env_decimal("KIE_WAN_27_IMAGE_1K_USD", "0.05"),
        wan_27_2k_usd=_env_decimal("KIE_WAN_27_IMAGE_2K_USD", "0.08"),
        flux_2_pro_1k_usd=_env_decimal("KIE_FLUX_2_PRO_IMAGE_1K_USD", "0.045"),
        flux_2_pro_2k_usd=_env_decimal("KIE_FLUX_2_PRO_IMAGE_2K_USD", "0.075"),
        grok_480p_usd_per_second=_env_decimal(
            "KIE_GROK_480P_USD_PER_SECOND", "0.008"
        ),
        grok_720p_usd_per_second=_env_decimal(
            "KIE_GROK_720P_USD_PER_SECOND", "0.015"
        ),
        grok_15_480p_usd_per_second=_env_decimal(
            "KIE_GROK_15_480P_USD_PER_SECOND", "0.0725"
        ),
        grok_15_720p_usd_per_second=_env_decimal(
            "KIE_GROK_15_720P_USD_PER_SECOND", "0.125"
        ),
        seedance_480p_no_audio_usd_per_second=_env_decimal(
            "KIE_SEEDANCE_15_480P_NO_AUDIO_USD_PER_SECOND", "0.00875"
        ),
        seedance_720p_no_audio_usd_per_second=_env_decimal(
            "KIE_SEEDANCE_15_720P_NO_AUDIO_USD_PER_SECOND", "0.0175"
        ),
        seedance_1080p_no_audio_usd_per_second=_env_decimal(
            "KIE_SEEDANCE_15_1080P_NO_AUDIO_USD_PER_SECOND", "0.0375"
        ),
        seedance_480p_audio_usd_per_second=_env_decimal(
            "KIE_SEEDANCE_15_480P_AUDIO_USD_PER_SECOND", "0.0175"
        ),
        seedance_720p_audio_usd_per_second=_env_decimal(
            "KIE_SEEDANCE_15_720P_AUDIO_USD_PER_SECOND", "0.035"
        ),
        seedance_1080p_audio_usd_per_second=_env_decimal(
            "KIE_SEEDANCE_15_1080P_AUDIO_USD_PER_SECOND", "0.075"
        ),
        wan_720p_usd_per_second=_env_decimal_with_legacy(
            "KIE_WAN_27_720P_USD_PER_SECOND",
            "KIE_WAN_26_720P_USD_PER_SECOND",
            "0.08",
        ),
        wan_1080p_usd_per_second=_env_decimal_with_legacy(
            "KIE_WAN_27_1080P_USD_PER_SECOND",
            "KIE_WAN_26_1080P_USD_PER_SECOND",
            "0.12",
        ),
    )
    return KieSettings(
        enabled=enabled,
        api_key=api_key,
        base_url=base_url,
        file_upload_base_url=file_upload_base_url,
        grs_api_key=grs_api_key,
        grs_base_url=grs_base_url,
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
        credit_usd=credit_usd,
        credit_byn=credit_byn,
        max_concurrent_generations=parse_bounded_integer(
            os.getenv("KIE_MAX_CONCURRENT_GENERATIONS", "4"),
            variable_name="KIE_MAX_CONCURRENT_GENERATIONS",
            default=4,
            minimum=1,
            maximum=8,
        ),
        generation_max_attempts=parse_bounded_integer(
            os.getenv("KIE_GENERATION_MAX_ATTEMPTS", "50"),
            variable_name="KIE_GENERATION_MAX_ATTEMPTS",
            default=50,
            minimum=1,
            maximum=50,
        ),
    )


def _env_decimal(variable_name: str, default: str) -> Decimal:
    return _parse_non_negative_decimal(
        os.getenv(variable_name, "").strip() or default,
        variable_name=variable_name,
    )


def _env_decimal_with_legacy(
    variable_name: str, legacy_variable_name: str, default: str
) -> Decimal:
    value = (
        os.getenv(variable_name, "").strip()
        or os.getenv(legacy_variable_name, "").strip()
        or default
    )
    return _parse_non_negative_decimal(value, variable_name=variable_name)


def _parse_non_negative_decimal(value: str, *, variable_name: str) -> Decimal:
    try:
        result = Decimal(value.strip())
    except (InvalidOperation, ValueError) as error:
        raise RuntimeError(f"{variable_name} должен быть десятичным числом.") from error
    if not result.is_finite() or result < 0:
        raise RuntimeError(f"{variable_name} не может быть отрицательным.")
    return result


__all__ = ("KieSettings", "load_kie_settings")
