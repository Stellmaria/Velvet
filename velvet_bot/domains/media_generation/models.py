from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_UP
from enum import StrEnum
from typing import Any, Mapping

KIE_GENERATION_TASK_TYPE = "media.generate.kie"
_MONEY_QUANTUM = Decimal("0.01")


class KieModelAlias(StrEnum):
    SEEDREAM_5_PRO = "seedream_5_pro"
    NANO_BANANA_PRO = "nano_banana_pro"
    GROK_IMAGINE_VIDEO = "grok_imagine_video"

    @property
    def title(self) -> str:
        return {
            self.SEEDREAM_5_PRO: "Seedream 5 Pro",
            self.NANO_BANANA_PRO: "Nano Banana Pro",
            self.GROK_IMAGINE_VIDEO: "Grok Imagine Video",
        }[self]

    @property
    def is_video(self) -> bool:
        return self is self.GROK_IMAGINE_VIDEO


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
    seedream_5_pro: str
    nano_banana_pro: str = "nano-banana-pro"
    grok_imagine_video: str = "grok-imagine/text-to-video"

    def provider_model(self, alias: KieModelAlias) -> str:
        mapping = {
            KieModelAlias.SEEDREAM_5_PRO: self.seedream_5_pro,
            KieModelAlias.NANO_BANANA_PRO: self.nano_banana_pro,
            KieModelAlias.GROK_IMAGINE_VIDEO: self.grok_imagine_video,
        }
        model = mapping[alias].strip()
        if not model:
            raise ValueError(f"Для {alias.value} не задан model id Kie.ai.")
        return model


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
                if request.quality.casefold() == "high"
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
class KieGenerationRequest:
    model: KieModelAlias
    prompt: str
    aspect_ratio: str = "9:16"
    resolution: str = "1K"
    quality: str = "basic"
    duration_seconds: int = 6
    image_urls: tuple[str, ...] = ()
    output_format: str = "png"
    mode: str = "normal"
    extra_input: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("Промт Kie.ai не может быть пустым.")
        if not self.aspect_ratio.strip():
            raise ValueError("Соотношение сторон Kie.ai не может быть пустым.")
        if self.duration_seconds <= 0:
            raise ValueError("Длительность видео должна быть положительной.")
        if any(not url.strip() for url in self.image_urls):
            raise ValueError("URL референсов Kie.ai не могут быть пустыми.")

    def to_input(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "prompt": self.prompt.strip(),
            "aspect_ratio": self.aspect_ratio.strip(),
        }
        if self.model is KieModelAlias.SEEDREAM_5_PRO:
            payload.update(
                {
                    "quality": self.quality.strip() or "basic",
                    "image_urls": list(self.image_urls),
                }
            )
        elif self.model is KieModelAlias.NANO_BANANA_PRO:
            payload.update(
                {
                    "resolution": self.resolution.strip() or "1K",
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
            "prompt": self.prompt.strip(),
            "aspect_ratio": self.aspect_ratio.strip(),
            "resolution": self.resolution.strip(),
            "quality": self.quality.strip(),
            "duration_seconds": self.duration_seconds,
            "image_urls": list(self.image_urls),
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
        try:
            model = KieModelAlias(model_text)
        except ValueError as error:
            raise ValueError(f"Неизвестная Kie-модель в очереди: {model_text}") from error
        image_urls_value = payload.get("image_urls")
        image_urls = (
            tuple(
                str(item).strip()
                for item in image_urls_value
                if str(item).strip()
            )
            if isinstance(image_urls_value, (list, tuple))
            else ()
        )
        extra_value = payload.get("extra_input")
        extra_input = dict(extra_value) if isinstance(extra_value, Mapping) else {}
        return cls(
            model=model,
            prompt=str(payload.get("prompt") or "").strip(),
            aspect_ratio=str(payload.get("aspect_ratio") or "9:16").strip(),
            resolution=str(payload.get("resolution") or "1K").strip(),
            quality=str(payload.get("quality") or "basic").strip(),
            duration_seconds=_positive_int(payload.get("duration_seconds"), default=6),
            image_urls=image_urls,
            output_format=str(payload.get("output_format") or "png").strip(),
            mode=str(payload.get("mode") or "normal").strip(),
            extra_input=extra_input,
        )


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
        return cls(
            task_id=task_id,
            state=state,
            result_urls=result_urls,
            consumed_credits=_non_negative_int(data.get("consumeCredits")),
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


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


__all__ = (
    "KIE_GENERATION_TASK_TYPE",
    "KieGenerationRequest",
    "KieModelAlias",
    "KieModelCatalog",
    "KiePricing",
    "KieTaskRecord",
    "KieTaskState",
)
