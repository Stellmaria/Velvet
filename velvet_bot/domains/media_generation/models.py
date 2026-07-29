from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from decimal import Decimal, ROUND_UP
from enum import StrEnum
from typing import Any, Mapping

KIE_GENERATION_TASK_TYPE = "media.generate.kie"
MAX_KIE_REFERENCES = 5
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


class KieModelAlias(StrEnum):
    SEEDREAM_5_PRO = "seedream_5_pro"
    NANO_BANANA_PRO = "nano_banana_pro"
    GROK_IMAGINE_VIDEO = "grok_imagine_video"

    @property
    def display_name(self) -> str:
        return {
            self.SEEDREAM_5_PRO: "Seedream 5 Pro",
            self.NANO_BANANA_PRO: "Nano Banana Pro",
            self.GROK_IMAGINE_VIDEO: "Grok Imagine Video",
        }[self]

    @property
    def is_video(self) -> bool:
        return self is self.GROK_IMAGINE_VIDEO

    @property
    def supported_photo_resolutions(self) -> tuple[str, ...]:
        if self is self.NANO_BANANA_PRO:
            return ("1K", "2K", "4K")
        if self is self.SEEDREAM_5_PRO:
            return ("1K", "2K")
        return ()

    @property
    def supports_provider_mature_override(self) -> bool:
        return self is self.SEEDREAM_5_PRO


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
    """Provider model ids separated from stable internal aliases.

    ``seedream_5_pro`` is retained as a legacy fallback for existing server
    environments. New deployments should set the explicit text and image ids.
    """

    seedream_5_pro: str = ""
    seedream_5_pro_text: str = ""
    seedream_5_pro_image: str = ""
    nano_banana_pro: str = "nano-banana-pro"
    grok_imagine_video: str = "grok-imagine/text-to-video"

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
        elif alias is KieModelAlias.NANO_BANANA_PRO:
            model = self.nano_banana_pro
        else:
            model = self.grok_imagine_video
        normalized = model.strip()
        if not normalized:
            mode_suffix = f" для режима {input_mode.value}" if input_mode else ""
            raise ValueError(
                f"Для {alias.value}{mode_suffix} не задан model id Kie.ai."
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
    nano_1k_2k_usd: Decimal = Decimal("0.09")
    nano_4k_usd: Decimal = Decimal("0.12")
    grok_480p_usd_per_second: Decimal = Decimal("0.008")
    grok_720p_usd_per_second: Decimal = Decimal("0.015")

    def estimate_usd(self, request: "KieGenerationRequest") -> Decimal:
        if request.model is KieModelAlias.SEEDREAM_5_PRO:
            return (
                self.seedream_high_usd
                if request.resolution.casefold() == "2k"
                else self.seedream_basic_usd
            )
        if request.model is KieModelAlias.NANO_BANANA_PRO:
            return (
                self.nano_4k_usd
                if request.resolution.casefold() == "4k"
                else self.nano_1k_2k_usd
            )
        if request.model is KieModelAlias.GROK_IMAGINE_VIDEO:
            rate = (
                self.grok_720p_usd_per_second
                if request.resolution.casefold() == "720p"
                else self.grok_480p_usd_per_second
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
            raise ValueError("Курс USD/RUB для Kie.ai должен быть больше нуля.")
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

    def __post_init__(self) -> None:
        if not self.telegram_file_id.strip():
            raise ValueError("Telegram file_id референса не может быть пустым.")
        if self.source not in {"library", "upload"}:
            raise ValueError("Источник референса должен быть library или upload.")
        normalized_mime = self.mime_type.strip().casefold()
        if normalized_mime not in {
            "image/jpeg",
            "image/jpg",
            "image/png",
            "image/webp",
        }:
            raise ValueError("Kie принимает референсы только JPG, PNG или WEBP.")
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
            raise ValueError("Соотношение сторон Kie.ai не может быть пустым.")
        if self.duration_seconds <= 0:
            raise ValueError("Длительность видео должна быть положительной.")
        if len(self.references) > MAX_KIE_REFERENCES:
            raise ValueError("Можно использовать не больше пяти референсов.")
        if any(not url.strip() for url in self.image_urls):
            raise ValueError("URL референсов Kie.ai не могут быть пустыми.")
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
        if not self.model.is_video:
            supported = self.model.supported_photo_resolutions
            if self.resolution.upper() not in supported:
                raise ValueError(
                    f"{self.model.display_name} не поддерживает качество "
                    f"{self.resolution}."
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

    def to_input(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "prompt": self.provider_prompt,
            "aspect_ratio": self.aspect_ratio.strip(),
        }
        if self.model is KieModelAlias.SEEDREAM_5_PRO:
            payload.update(
                {
                    "quality": self.provider_quality,
                    "nsfw_checker": self.content_mode is not KieContentMode.MATURE,
                }
            )
            if self.input_mode is not KieInputMode.TEXT:
                payload["image_urls"] = list(self.image_urls)
            payload["output_format"] = self.output_format.strip() or "png"
        elif self.model is KieModelAlias.NANO_BANANA_PRO:
            payload.update(
                {
                    "resolution": self.resolution.upper(),
                    "output_format": self.output_format.strip() or "png",
                    "image_input": list(self.image_urls),
                }
            )
        elif self.model is KieModelAlias.GROK_IMAGINE_VIDEO:
            payload.update(
                {
                    "resolution": self.resolution.strip() or "480p",
                    "duration": self.duration_seconds,
                    "mode": self.mode.strip() or "normal",
                    "image_urls": list(self.image_urls),
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
            raise ValueError("Неизвестные параметры Kie-задачи в очереди.") from error
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
