from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from decimal import Decimal, ROUND_UP
from enum import StrEnum
from typing import Any, Mapping

KIE_GENERATION_TASK_TYPE = "media.generate.kie"
# Collection happens before the user chooses a model. This is the highest
# documented input limit among the currently exposed photo editors.
MAX_KIE_REFERENCES = 10
MAX_KIE_REFERENCE_BYTES = 10 * 1024 * 1024
_MONEY_QUANTUM = Decimal("0.01")
_PHOTO_ONLY_PROMPT = (
    "Use the supplied reference image or images as the complete instruction. "
    "Preserve the subjects, identity, composition, colors and important visual "
    "details while producing one coherent high-quality image."
)


class KieInputMode(StrEnum):
    TEXT = "text"
    PHOTO = "photo"
    PHOTO_TEXT = "photo_text"

    @property
    def display_name(self) -> str:
        return {
            self.TEXT: "Текст",
            self.PHOTO: "Фото",
            self.PHOTO_TEXT: "Фото + текст",
        }[self]


class KieContentMode(StrEnum):
    MATURE = "mature"
    STANDARD = "standard"

    @property
    def display_name(self) -> str:
        return "Mature" if self is self.MATURE else "Стандартный"


@dataclass(frozen=True, slots=True)
class KiePhotoModelCapabilities:
    """Provider-backed constraints used by Telegram UI and request validation."""

    max_references: int
    prompt_limit: int
    resolutions: tuple[str, ...]
    aspect_ratios: tuple[str, ...]
    default_aspect_ratio: str
    supports_provider_mature_override: bool = False

    def __post_init__(self) -> None:
        if self.max_references <= 0:
            raise ValueError("Лимит референсов должен быть положительным.")
        if self.prompt_limit <= 0:
            raise ValueError("Лимит промта должен быть положительным.")
        if not self.resolutions:
            raise ValueError("Фото-модель должна поддерживать хотя бы одно качество.")
        if not self.aspect_ratios:
            raise ValueError("Фото-модель должна поддерживать хотя бы одно соотношение.")
        if self.default_aspect_ratio not in self.aspect_ratios:
            raise ValueError("Соотношение по умолчанию должно быть в списке доступных.")


class KieModelAlias(StrEnum):
    SEEDREAM_5_PRO = "seedream_5_pro"
    NANO_BANANA_2 = "nano_banana_2"
    NANO_BANANA_PRO = "nano_banana_pro"
    QWEN2_IMAGE_EDIT = "qwen2_image_edit"
    WAN_27_IMAGE = "wan_27_image"
    WAN_27_IMAGE_PRO = "wan_27_image_pro"
    FLUX_2_PRO_IMAGE = "flux_2_pro_image"
    GROK_IMAGINE_VIDEO = "grok_imagine_video"
    GROK_IMAGINE_VIDEO_15 = "grok_imagine_video_15"
    SEEDANCE_15_PRO_VIDEO = "seedance_15_pro_video"
    WAN_26_IMAGE_TO_VIDEO = "wan_26_image_to_video"

    @property
    def display_name(self) -> str:
        return {
            self.SEEDREAM_5_PRO: "Seedream 5 Pro",
            self.NANO_BANANA_2: "Nano Banana 2",
            self.NANO_BANANA_PRO: "Nano Banana Pro",
            self.QWEN2_IMAGE_EDIT: "Qwen Image 2.0",
            self.WAN_27_IMAGE: "Wan 2.7",
            self.WAN_27_IMAGE_PRO: "Wan 2.7 Pro",
            self.FLUX_2_PRO_IMAGE: "FLUX.2 Pro",
            self.GROK_IMAGINE_VIDEO: "Grok Imagine v1",
            self.GROK_IMAGINE_VIDEO_15: "Grok Imagine Video 1.5",
            self.SEEDANCE_15_PRO_VIDEO: "Seedance 1.5 Pro",
            self.WAN_26_IMAGE_TO_VIDEO: "Wan 2.7",
        }[self]

    @property
    def is_video(self) -> bool:
        return self in {
            self.GROK_IMAGINE_VIDEO,
            self.GROK_IMAGINE_VIDEO_15,
            self.SEEDANCE_15_PRO_VIDEO,
            self.WAN_26_IMAGE_TO_VIDEO,
        }

    @property
    def is_grs(self) -> bool:
        return self in {self.NANO_BANANA_2, self.NANO_BANANA_PRO}

    @property
    def provider_name(self) -> str:
        return "grs" if self.is_grs else "kie"

    @property
    def photo_capabilities(self) -> KiePhotoModelCapabilities | None:
        return _PHOTO_MODEL_CAPABILITIES.get(self)

    @property
    def is_photo_model(self) -> bool:
        return self.photo_capabilities is not None

    @property
    def supported_photo_resolutions(self) -> tuple[str, ...]:
        capabilities = self.photo_capabilities
        return capabilities.resolutions if capabilities is not None else ()

    @property
    def supported_aspect_ratios(self) -> tuple[str, ...]:
        capabilities = self.photo_capabilities
        return capabilities.aspect_ratios if capabilities is not None else ()

    @property
    def max_photo_references(self) -> int:
        capabilities = self.photo_capabilities
        return capabilities.max_references if capabilities is not None else 0

    @property
    def photo_prompt_limit(self) -> int:
        capabilities = self.photo_capabilities
        return capabilities.prompt_limit if capabilities is not None else 0

    @property
    def default_photo_aspect_ratio(self) -> str:
        capabilities = self.photo_capabilities
        return capabilities.default_aspect_ratio if capabilities is not None else "9:16"

    @property
    def supports_provider_mature_override(self) -> bool:
        capabilities = self.photo_capabilities
        return bool(
            capabilities is not None
            and capabilities.supports_provider_mature_override
        )


_COMMON_RATIOS = ("1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9")
_PHOTO_MODEL_CAPABILITIES: dict[KieModelAlias, KiePhotoModelCapabilities] = {
    KieModelAlias.SEEDREAM_5_PRO: KiePhotoModelCapabilities(
        max_references=10,
        prompt_limit=8000,
        resolutions=("1K", "2K"),
        aspect_ratios=("1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"),
        default_aspect_ratio="9:16",
        supports_provider_mature_override=True,
    ),
    # GRS exposes an images array but does not publish a hard maximum. Keep the
    # previous production contract of five until the provider documents more.
    KieModelAlias.NANO_BANANA_2: KiePhotoModelCapabilities(
        max_references=5,
        prompt_limit=8000,
        resolutions=("1K", "2K", "4K"),
        aspect_ratios=_COMMON_RATIOS,
        default_aspect_ratio="9:16",
    ),
    KieModelAlias.NANO_BANANA_PRO: KiePhotoModelCapabilities(
        max_references=5,
        prompt_limit=8000,
        resolutions=("1K", "2K", "4K"),
        aspect_ratios=_COMMON_RATIOS,
        default_aspect_ratio="9:16",
    ),
    KieModelAlias.WAN_27_IMAGE: KiePhotoModelCapabilities(
        max_references=9,
        prompt_limit=5000,
        resolutions=("1K", "2K"),
        aspect_ratios=("1:1", "3:4", "4:3", "1:8", "8:1", "9:16", "16:9", "21:9"),
        default_aspect_ratio="9:16",
        supports_provider_mature_override=True,
    ),
    KieModelAlias.WAN_27_IMAGE_PRO: KiePhotoModelCapabilities(
        max_references=9,
        prompt_limit=5000,
        resolutions=("1K", "2K", "4K"),
        aspect_ratios=("1:1", "3:4", "4:3", "1:8", "8:1", "9:16", "16:9", "21:9"),
        default_aspect_ratio="9:16",
        supports_provider_mature_override=True,
    ),
}


class KieTaskState(StrEnum):
    WAITING = "waiting"
    QUEUING = "queuing"
    GENERATING = "generating"
    SUCCESS = "success"
    FAIL = "fail"

    @property
    def terminal(self) -> bool:
        return self in {self.SUCCESS, self.FAIL}


@dataclass(frozen=True, slots=True)
class KieModelCatalog:
    """Provider model ids separated from stable internal aliases."""

    seedream_5_pro: str = ""
    seedream_5_pro_text: str = ""
    seedream_5_pro_image: str = ""
    nano_banana_2: str = "nano-banana-2"
    nano_banana_pro: str = "nano-banana-pro"
    wan_27_image: str = "wan/2-7-image"
    wan_27_image_pro: str = "wan/2-7-image-pro"
    grok_imagine_video: str = "grok-imagine/image-to-video"
    grok_imagine_video_15: str = "grok-imagine-video-1-5-preview"
    seedance_15_pro_video: str = "bytedance/seedance-1.5-pro"
    wan_26_image_to_video: str = "wan/2-7-image-to-video"

    def provider_model(
        self,
        alias: KieModelAlias,
        *,
        input_mode: KieInputMode | None = None,
    ) -> str:
        if alias is KieModelAlias.SEEDREAM_5_PRO:
            if input_mode is KieInputMode.TEXT:
                legacy_text = (
                    self.seedream_5_pro
                    if "text-to-image" in self.seedream_5_pro.casefold()
                    else ""
                )
                model = self.seedream_5_pro_text or legacy_text
            else:
                model = self.seedream_5_pro_image or self.seedream_5_pro
        elif alias is KieModelAlias.NANO_BANANA_2:
            model = self.nano_banana_2
        elif alias is KieModelAlias.NANO_BANANA_PRO:
            model = self.nano_banana_pro
        elif alias is KieModelAlias.WAN_27_IMAGE:
            model = self.wan_27_image
        elif alias is KieModelAlias.WAN_27_IMAGE_PRO:
            model = self.wan_27_image_pro
        elif alias is KieModelAlias.GROK_IMAGINE_VIDEO:
            model = self.grok_imagine_video
        elif alias is KieModelAlias.GROK_IMAGINE_VIDEO_15:
            model = self.grok_imagine_video_15
        elif alias is KieModelAlias.SEEDANCE_15_PRO_VIDEO:
            model = self.seedance_15_pro_video
        elif alias is KieModelAlias.WAN_26_IMAGE_TO_VIDEO:
            model = self.wan_26_image_to_video
        else:
            raise ValueError(f"Неизвестная модель: {alias}")
        normalized = model.strip()
        if not normalized:
            mode_suffix = f" для режима {input_mode.value}" if input_mode else ""
            provider = "GRS AI" if alias.is_grs else "Kie.ai"
            raise ValueError(
                f"Для {alias.value}{mode_suffix} не задан model id {provider}."
            )
        return normalized

    def provider_model_for_request(self, request: "KieGenerationRequest") -> str:
        return self.provider_model(
            request.model,
            input_mode=request.input_mode,
        )


@dataclass(frozen=True, slots=True)
class KiePricing:
    seedream_basic_usd: Decimal = Decimal("0.075")
    seedream_high_usd: Decimal = Decimal("0.15")
    # Legacy Kie values remain for environment compatibility.
    nano_1k_2k_usd: Decimal = Decimal("0.09")
    nano_4k_usd: Decimal = Decimal("0.12")
    # Conservative USD-equivalent budget estimates for GRS billing.
    nano_banana_2_usd: Decimal = Decimal("0.02")
    nano_banana_pro_usd: Decimal | None = None
    # Configurable preflight estimates. Provider billing remains the source of truth.
    wan_27_1k_usd: Decimal = Decimal("0.03")
    wan_27_2k_usd: Decimal = Decimal("0.03")
    wan_27_pro_1k_usd: Decimal = Decimal("0.075")
    wan_27_pro_2k_usd: Decimal = Decimal("0.075")
    wan_27_pro_4k_usd: Decimal = Decimal("0.075")
    grok_480p_usd_per_second: Decimal = Decimal("0.008")
    grok_720p_usd_per_second: Decimal = Decimal("0.015")
    grok_15_480p_usd_per_second: Decimal = Decimal("0.0725")
    grok_15_720p_usd_per_second: Decimal = Decimal("0.125")
    seedance_480p_no_audio_usd_per_second: Decimal = Decimal("0.00875")
    seedance_720p_no_audio_usd_per_second: Decimal = Decimal("0.0175")
    seedance_1080p_no_audio_usd_per_second: Decimal = Decimal("0.0375")
    seedance_480p_audio_usd_per_second: Decimal = Decimal("0.0175")
    seedance_720p_audio_usd_per_second: Decimal = Decimal("0.035")
    seedance_1080p_audio_usd_per_second: Decimal = Decimal("0.075")
    wan_720p_usd_per_second: Decimal = Decimal("0.07")
    wan_1080p_usd_per_second: Decimal = Decimal("0.105")

    def estimate_usd(self, request: "KieGenerationRequest") -> Decimal:
        if request.model is KieModelAlias.SEEDREAM_5_PRO:
            return (
                self.seedream_high_usd
                if request.resolution.casefold() == "2k"
                else self.seedream_basic_usd
            )
        if request.model is KieModelAlias.NANO_BANANA_2:
            return self.nano_banana_2_usd
        if request.model is KieModelAlias.NANO_BANANA_PRO:
            if self.nano_banana_pro_usd is not None:
                return self.nano_banana_pro_usd
            return (
                self.nano_4k_usd
                if request.resolution.casefold() == "4k"
                else self.nano_1k_2k_usd
            )
        if request.model is KieModelAlias.WAN_27_IMAGE:
            return (
                self.wan_27_2k_usd
                if request.resolution.casefold() == "2k"
                else self.wan_27_1k_usd
            )
        if request.model is KieModelAlias.WAN_27_IMAGE_PRO:
            return {
                "2k": self.wan_27_pro_2k_usd,
                "4k": self.wan_27_pro_4k_usd,
            }.get(request.resolution.casefold(), self.wan_27_pro_1k_usd)
        if request.model is KieModelAlias.GROK_IMAGINE_VIDEO:
            rate = (
                self.grok_720p_usd_per_second
                if request.resolution.casefold() == "720p"
                else self.grok_480p_usd_per_second
            )
            return rate * Decimal(request.duration_seconds)
        if request.model is KieModelAlias.GROK_IMAGINE_VIDEO_15:
            rate = (
                self.grok_15_720p_usd_per_second
                if request.resolution.casefold() == "720p"
                else self.grok_15_480p_usd_per_second
            )
            return rate * Decimal(request.duration_seconds)
        if request.model is KieModelAlias.SEEDANCE_15_PRO_VIDEO:
            audio = bool(request.extra_input.get("generate_audio", False))
            resolution = request.resolution.casefold()
            if audio:
                rate = {
                    "480p": self.seedance_480p_audio_usd_per_second,
                    "720p": self.seedance_720p_audio_usd_per_second,
                    "1080p": self.seedance_1080p_audio_usd_per_second,
                }.get(resolution, self.seedance_720p_audio_usd_per_second)
            else:
                rate = {
                    "480p": self.seedance_480p_no_audio_usd_per_second,
                    "720p": self.seedance_720p_no_audio_usd_per_second,
                    "1080p": self.seedance_1080p_no_audio_usd_per_second,
                }.get(resolution, self.seedance_720p_no_audio_usd_per_second)
            return rate * Decimal(request.duration_seconds)
        if request.model is KieModelAlias.WAN_26_IMAGE_TO_VIDEO:
            rate = (
                self.wan_1080p_usd_per_second
                if request.resolution.casefold() == "1080p"
                else self.wan_720p_usd_per_second
            )
            return rate * Decimal(request.duration_seconds)
        raise ValueError(f"Неизвестная модель: {request.model}")

    def estimate_rub(
        self,
        request: "KieGenerationRequest",
        *,
        usd_to_rub: Decimal,
    ) -> Decimal:
        if usd_to_rub <= 0:
            raise ValueError("Курс USD/RUB для AI-генерации должен быть больше нуля.")
        return (self.estimate_usd(request) * usd_to_rub).quantize(
            _MONEY_QUANTUM,
            rounding=ROUND_UP,
        )


@dataclass(frozen=True, slots=True)
class KieReferenceImage:
    telegram_file_id: str
    source: str
    telegram_file_unique_id: str | None = None
    mime_type: str = "image/jpeg"
    file_name: str = "reference.jpg"
    file_size: int | None = None
    character_id: int | None = None
    reference_id: int | None = None
    workspace_id: int | None = None

    def __post_init__(self) -> None:
        if not self.telegram_file_id.strip():
            raise ValueError("Telegram file_id референса не может быть пустым.")
        if self.source not in {"library", "upload", "system", "personal"}:
            raise ValueError(
                "Источник референса должен быть library, upload, system или personal."
            )
        normalized_mime = self.mime_type.strip().casefold()
        if normalized_mime not in {
            "image/jpeg",
            "image/jpg",
            "image/png",
            "image/webp",
        }:
            raise ValueError("Провайдер принимает референсы только JPG, PNG или WEBP.")
        if self.file_size is not None and self.file_size > MAX_KIE_REFERENCE_BYTES:
            raise ValueError("Референс должен быть не больше 10 МБ.")

    def to_payload(self) -> dict[str, object]:
        return {
            "telegram_file_id": self.telegram_file_id,
            "telegram_file_unique_id": self.telegram_file_unique_id,
            "source": self.source,
            "mime_type": self.mime_type,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "character_id": self.character_id,
            "reference_id": self.reference_id,
            "workspace_id": self.workspace_id,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "KieReferenceImage":
        return cls(
            telegram_file_id=str(payload.get("telegram_file_id") or "").strip(),
            telegram_file_unique_id=_optional_text(
                payload.get("telegram_file_unique_id")
            ),
            source=str(payload.get("source") or "upload").strip(),
            mime_type=str(payload.get("mime_type") or "image/jpeg").strip(),
            file_name=str(payload.get("file_name") or "reference.jpg").strip(),
            file_size=_optional_int(payload.get("file_size")),
            character_id=_optional_int(payload.get("character_id")),
            reference_id=_optional_int(payload.get("reference_id")),
            workspace_id=_optional_int(payload.get("workspace_id")),
        )


@dataclass(frozen=True, slots=True)
class KieGenerationRequest:
    model: KieModelAlias
    input_mode: KieInputMode = KieInputMode.TEXT
    prompt: str = ""
    references: tuple[KieReferenceImage, ...] = ()
    content_mode: KieContentMode = KieContentMode.MATURE
    aspect_ratio: str = "9:16"
    resolution: str = "1K"
    duration_seconds: int = 6
    image_urls: tuple[str, ...] = ()
    output_format: str = "png"
    mode: str = "normal"
    extra_input: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        prompt = self.prompt.strip()
        if not self.aspect_ratio.strip():
            raise ValueError("Соотношение сторон не может быть пустым.")
        if self.duration_seconds <= 0:
            raise ValueError("Длительность видео должна быть положительной.")
        if len(self.references) > MAX_KIE_REFERENCES:
            raise ValueError(
                f"Можно использовать не больше {MAX_KIE_REFERENCES} референсов."
            )
        if any(not url.strip() for url in self.image_urls):
            raise ValueError("URL референсов не могут быть пустыми.")
        if self.input_mode is KieInputMode.TEXT:
            if not prompt:
                raise ValueError("Для режима Текст нужен промт.")
            if self.references:
                raise ValueError("Режим Текст не должен содержать референсы.")
        elif self.input_mode is KieInputMode.PHOTO:
            if not self.references:
                raise ValueError("Для режима Фото нужен хотя бы один референс.")
        elif self.input_mode is KieInputMode.PHOTO_TEXT:
            if not self.references or not prompt:
                raise ValueError("Для режима Фото + текст нужны фото и промт.")
        if self.model.is_photo_model:
            capabilities = self.model.photo_capabilities
            assert capabilities is not None
            if len(self.references) > capabilities.max_references:
                raise ValueError(
                    f"{self.model.display_name} принимает не больше "
                    f"{capabilities.max_references} референсов."
                )
            if len(prompt) > capabilities.prompt_limit:
                raise ValueError(
                    f"{self.model.display_name} принимает промт не длиннее "
                    f"{capabilities.prompt_limit} символов."
                )
            if self.resolution.upper() not in capabilities.resolutions:
                raise ValueError(
                    f"{self.model.display_name} не поддерживает качество "
                    f"{self.resolution}."
                )
            if self.aspect_ratio not in capabilities.aspect_ratios:
                raise ValueError(
                    f"{self.model.display_name} не поддерживает соотношение "
                    f"{self.aspect_ratio}."
                )
            if (
                self.model is KieModelAlias.WAN_27_IMAGE_PRO
                and self.resolution.upper() == "4K"
                and self.input_mode is not KieInputMode.TEXT
            ):
                raise ValueError(
                    "Wan 2.7 Pro поддерживает 4K только в режиме «Только текст»."
                )

    @property
    def provider_prompt(self) -> str:
        return self.prompt.strip() or _PHOTO_ONLY_PROMPT

    @property
    def provider_quality(self) -> str:
        return "high" if self.resolution.casefold() == "2k" else "basic"

    def with_image_urls(self, image_urls: tuple[str, ...]) -> "KieGenerationRequest":
        if len(image_urls) != len(self.references):
            raise ValueError("Количество загруженных URL не совпадает с референсами.")
        return replace(self, image_urls=image_urls)

    def to_grs_input(self, *, model_id: str) -> dict[str, object]:
        if not self.model.is_grs:
            raise ValueError("GRS payload доступен только для Nano Banana 2/Pro.")
        return {
            "model": model_id.strip(),
            "prompt": self.provider_prompt,
            "images": list(self.image_urls),
            "aspectRatio": self.aspect_ratio.strip(),
            "imageSize": self.resolution.upper(),
            "replyType": "json",
        }

    def to_input(self) -> dict[str, object]:
        payload: dict[str, object] = {"prompt": self.provider_prompt}
        mature_override = self.content_mode is not KieContentMode.MATURE
        if self.model is KieModelAlias.SEEDREAM_5_PRO:
            payload.update(
                {
                    "aspect_ratio": self.aspect_ratio.strip(),
                    "quality": self.provider_quality,
                    "nsfw_checker": mature_override,
                }
            )
            if self.input_mode is not KieInputMode.TEXT:
                payload["image_urls"] = list(self.image_urls)
            payload["output_format"] = self.output_format.strip() or "png"
        elif self.model in {
            KieModelAlias.NANO_BANANA_2,
            KieModelAlias.NANO_BANANA_PRO,
        }:
            payload.update(
                {
                    "aspect_ratio": self.aspect_ratio.strip(),
                    "resolution": self.resolution.upper(),
                    "output_format": self.output_format.strip() or "png",
                    "image_input": list(self.image_urls),
                }
            )
        elif self.model in {
            KieModelAlias.WAN_27_IMAGE,
            KieModelAlias.WAN_27_IMAGE_PRO,
        }:
            payload.update(
                {
                    "input_urls": list(self.image_urls),
                    "bbox_list": [[] for _ in self.image_urls],
                    "enable_sequential": False,
                    "thinking_mode": False,
                    "n": 1,
                    "resolution": self.resolution.upper(),
                    "aspect_ratio": self.aspect_ratio.strip(),
                    "watermark": False,
                    "seed": 0,
                    "nsfw_checker": mature_override,
                }
            )
        elif self.model is KieModelAlias.GROK_IMAGINE_VIDEO:
            payload.update(
                {
                    "aspect_ratio": self.aspect_ratio.strip(),
                    "resolution": self.resolution.strip() or "480p",
                    "duration": self.duration_seconds,
                    "mode": self.mode.strip() or "normal",
                    "image_urls": list(self.image_urls),
                    "nsfw_checker": mature_override,
                }
            )
        elif self.model is KieModelAlias.GROK_IMAGINE_VIDEO_15:
            payload.update(
                {
                    "aspect_ratio": self.aspect_ratio.strip() or "auto",
                    "resolution": self.resolution.strip() or "480p",
                    "duration": self.duration_seconds,
                    "image_urls": list(self.image_urls),
                    "nsfw_checker": mature_override,
                }
            )
        elif self.model is KieModelAlias.SEEDANCE_15_PRO_VIDEO:
            payload.update(
                {
                    "input_urls": list(self.image_urls),
                    "aspect_ratio": self.aspect_ratio.strip(),
                    "resolution": self.resolution.strip() or "720p",
                    "duration": self.duration_seconds,
                    "fixed_lens": False,
                    "generate_audio": False,
                    "nsfw_checker": mature_override,
                }
            )
        elif self.model is KieModelAlias.WAN_26_IMAGE_TO_VIDEO:
            payload.update(
                {
                    "image_urls": list(self.image_urls),
                    "duration": str(self.duration_seconds),
                    "resolution": self.resolution.strip() or "720p",
                    "nsfw_checker": mature_override,
                }
            )
        payload.update(dict(self.extra_input))
        return payload

    def to_task_payload(self) -> dict[str, object]:
        return {
            "model": self.model.value,
            "input_mode": self.input_mode.value,
            "prompt": self.prompt.strip(),
            "references": [item.to_payload() for item in self.references],
            "content_mode": self.content_mode.value,
            "aspect_ratio": self.aspect_ratio.strip(),
            "resolution": self.resolution.strip(),
            "duration_seconds": self.duration_seconds,
            "output_format": self.output_format.strip(),
            "mode": self.mode.strip(),
            "extra_input": dict(self.extra_input),
        }

    @classmethod
    def from_task_payload(
        cls,
        payload: Mapping[str, object],
    ) -> "KieGenerationRequest":
        model_text = str(payload.get("model") or "").strip()
        input_mode_text = str(payload.get("input_mode") or "text").strip()
        content_mode_text = str(payload.get("content_mode") or "mature").strip()
        try:
            model = KieModelAlias(model_text)
            input_mode = KieInputMode(input_mode_text)
            content_mode = KieContentMode(content_mode_text)
        except ValueError as error:
            raise ValueError("Неизвестные параметры AI-задачи в очереди.") from error
        references_value = payload.get("references")
        references = (
            tuple(
                KieReferenceImage.from_payload(item)
                for item in references_value
                if isinstance(item, Mapping)
            )
            if isinstance(references_value, (list, tuple))
            else ()
        )
        extra_value = payload.get("extra_input")
        extra_input = dict(extra_value) if isinstance(extra_value, Mapping) else {}
        return cls(
            model=model,
            input_mode=input_mode,
            prompt=str(payload.get("prompt") or "").strip(),
            references=references,
            content_mode=content_mode,
            aspect_ratio=str(payload.get("aspect_ratio") or "9:16").strip(),
            resolution=str(payload.get("resolution") or "1K").strip(),
            duration_seconds=_positive_int(payload.get("duration_seconds"), default=6),
            output_format=str(payload.get("output_format") or "png").strip(),
            mode=str(payload.get("mode") or "normal").strip(),
            extra_input=extra_input,
        )


@dataclass(frozen=True, slots=True)
class KieUploadedFile:
    file_url: str
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None


@dataclass(frozen=True, slots=True)
class KieTaskRecord:
    task_id: str
    state: KieTaskState
    result_urls: tuple[str, ...] = ()
    consumed_credits: int = 0
    failure_code: str | None = None
    failure_message: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> "KieTaskRecord":
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ValueError("Kie.ai recordInfo не вернул объект data.")
        task_id = str(data.get("taskId") or "").strip()
        if not task_id:
            raise ValueError("Kie.ai recordInfo не вернул taskId.")
        state_text = str(data.get("state") or "waiting").strip().casefold()
        try:
            state = KieTaskState(state_text)
        except ValueError as error:
            raise ValueError(f"Неизвестное состояние Kie.ai: {state_text}") from error
        result_urls = _extract_result_urls(data.get("resultJson"))
        credits = data.get("creditsConsumed")
        if credits is None:
            credits = data.get("consumeCredits")
        return cls(
            task_id=task_id,
            state=state,
            result_urls=result_urls,
            consumed_credits=_non_negative_int(credits),
            failure_code=_optional_text(data.get("failCode")),
            failure_message=_optional_text(data.get("failMsg")),
            raw=dict(data),
        )

    @classmethod
    def from_grs_api(
        cls,
        payload: Mapping[str, Any],
        *,
        task_id: str | None = None,
    ) -> "KieTaskRecord":
        raw_task_id = str(payload.get("id") or "").strip()
        normalized_task_id = str(task_id or raw_task_id).strip()
        if not normalized_task_id:
            raise ValueError("GRS AI не вернул id задачи.")
        status = str(payload.get("status") or "").strip().casefold()
        state_map = {
            "waiting": KieTaskState.WAITING,
            "pending": KieTaskState.WAITING,
            "submitted": KieTaskState.WAITING,
            "queued": KieTaskState.QUEUING,
            "queuing": KieTaskState.QUEUING,
            "processing": KieTaskState.GENERATING,
            "running": KieTaskState.GENERATING,
            "generating": KieTaskState.GENERATING,
            "succeeded": KieTaskState.SUCCESS,
            "success": KieTaskState.SUCCESS,
            "completed": KieTaskState.SUCCESS,
            "failed": KieTaskState.FAIL,
            "fail": KieTaskState.FAIL,
            "error": KieTaskState.FAIL,
        }
        state = state_map.get(status)
        if state is None:
            raise ValueError(f"Неизвестное состояние GRS AI: {status or '<пусто>'}")
        results = payload.get("results")
        result_urls = (
            tuple(
                str(item.get("url") or "").strip()
                for item in results
                if isinstance(item, Mapping) and str(item.get("url") or "").strip()
            )
            if isinstance(results, (list, tuple))
            else ()
        )
        failure = payload.get("error")
        failure_message = _optional_text(
            failure.get("message") if isinstance(failure, Mapping) else failure
        ) or _optional_text(payload.get("message") or payload.get("msg"))
        failure_code = _optional_text(
            failure.get("code") if isinstance(failure, Mapping) else payload.get("code")
        )
        return cls(
            task_id=normalized_task_id,
            state=state,
            result_urls=result_urls,
            failure_code=failure_code,
            failure_message=failure_message,
            raw=dict(payload),
        )


def _extract_result_urls(value: object) -> tuple[str, ...]:
    parsed: object = value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return ()
    if not isinstance(parsed, Mapping):
        return ()
    urls = parsed.get("resultUrls")
    if not isinstance(urls, list):
        return ()
    return tuple(str(url).strip() for url in urls if str(url).strip())


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(str(value or "0").strip()))
    except (TypeError, ValueError):
        return 0


def _positive_int(value: object, *, default: int) -> int:
    parsed = _non_negative_int(value)
    return parsed if parsed > 0 else default


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
