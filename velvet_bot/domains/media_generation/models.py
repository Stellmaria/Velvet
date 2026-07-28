from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping


class KieModelAlias(StrEnum):
    SEEDREAM_5_PRO = "seedream_5_pro"
    NANO_BANANA_PRO = "nano_banana_pro"
    GROK_IMAGINE_VIDEO = "grok_imagine_video"


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
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


__all__ = (
    "KieGenerationRequest",
    "KieModelAlias",
    "KieModelCatalog",
    "KiePricing",
    "KieTaskRecord",
    "KieTaskState",
)
