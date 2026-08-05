from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import KieGenerationRequest, KieTaskRecord


class MediaProviderName(StrEnum):
    KIE = "kie"
    GRS = "grs"


class ProviderFailureKind(StrEnum):
    TRANSIENT = "transient"
    TERMINAL = "terminal"
    REFUSAL = "refusal"
    UNKNOWN_SUBMIT = "unknown_submit"


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    provider: MediaProviderName
    model_id: str


@dataclass(frozen=True, slots=True)
class MediaProviderUsage:
    provider: MediaProviderName
    provider_task_id: str
    consumed_credits: int
    result_count: int
    terminal_state: str


class MediaProviderAdapter(Protocol):
    provider: MediaProviderName

    def route(self, request: "KieGenerationRequest") -> ProviderRoute: ...

    async def submit(
        self,
        request: "KieGenerationRequest",
        *,
        callback_url: str | None = None,
    ) -> str: ...

    async def status(self, task_id: str) -> "KieTaskRecord": ...

    async def cancel(self, task_id: str) -> bool: ...

    async def balance(self) -> Decimal: ...

    def usage(self, record: "KieTaskRecord") -> MediaProviderUsage: ...


class MediaProviderRegistry:
    def __init__(self, adapters: Mapping[MediaProviderName, MediaProviderAdapter]) -> None:
        self._adapters = dict(adapters)
        missing = set(MediaProviderName) - set(self._adapters)
        if missing:
            raise ValueError(
                "Не зарегистрированы media provider adapters: "
                + ", ".join(sorted(item.value for item in missing))
            )

    def for_request(self, request: "KieGenerationRequest") -> MediaProviderAdapter:
        return self._adapters[MediaProviderName(request.model.provider_name)]

    def for_task_id(self, task_id: str) -> MediaProviderAdapter:
        provider = (
            MediaProviderName.GRS
            if str(task_id).strip().startswith("grs:")
            else MediaProviderName.KIE
        )
        return self._adapters[provider]

    def route(self, request: "KieGenerationRequest") -> ProviderRoute:
        return self.for_request(request).route(request)


_GRS_VIOLATION_STATUSES = frozenset(
    {"violation", "content_violation", "moderation_violation", "moderated"}
)
_CREDIT_KEYS = frozenset(
    {
        "credits",
        "credit",
        "balance",
        "currentcredits",
        "apikeycredits",
        "remainingcredits",
        "remaincredits",
        "availablecredits",
        "leftcredits",
    }
)
_REASON_KEYS = frozenset(
    {
        "message",
        "msg",
        "reason",
        "detail",
        "details",
        "blockedreason",
        "blockreason",
        "violationreason",
        "moderationreason",
        "safetyreason",
        "category",
        "categories",
        "code",
        "errorcode",
        "policy",
        "policycategory",
    }
)
_GENERIC_REASON_VALUES = frozenset(
    {
        "violation",
        "content violation",
        "content_violation",
        "moderation violation",
        "moderation_violation",
        "moderated",
        "failed",
        "fail",
        "error",
        "запрос отклонён модерацией grs ai.",
    }
)
_MODEL_CHATTER_MARKERS = (
    "я просто языковая модель",
    "я всего лишь языковая модель",
    "я просто генерирую текст",
    "я могу только генерировать текст",
    "мои возможности ограничены",
    "эта задача не для меня",
    "в моей программе нет таких возможностей",
    "не могу создавать изображения",
    "не умею создавать изображения",
    "as a language model",
    "i am just a language model",
    "i'm just a language model",
    "i can only generate text",
    "i only generate text",
    "my capabilities are limited",
    "this task is not for me",
    "i cannot generate images",
    "i can't generate images",
)
_IMAGE_OUTPUT_GUARD = (
    "Generate the requested image and return image output only. "
    "Do not answer with text, disclaimers, or descriptions of your capabilities. "
    "If the request cannot be completed, return the provider's structured failure "
    "status instead of conversational text."
)


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _decimal_value(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Mapping) or isinstance(value, (list, tuple, set)):
        return None
    text = str(value).strip().replace(" ", "").replace(",", "")
    if not text:
        return None
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def extract_provider_credits(value: object) -> Decimal | None:
    direct = _decimal_value(value)
    if direct is not None:
        return direct
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _normalized_key(key) in _CREDIT_KEYS:
                parsed = _decimal_value(item)
                if parsed is not None:
                    return parsed
        for item in value.values():
            if isinstance(item, (Mapping, list, tuple)):
                parsed = extract_provider_credits(item)
                if parsed is not None:
                    return parsed
    if isinstance(value, (list, tuple)):
        for item in value:
            parsed = extract_provider_credits(item)
            if parsed is not None:
                return parsed
    return None


def provider_reason_text(value: object) -> str | None:
    if value is None or isinstance(value, bool) or isinstance(value, Mapping):
        return None
    if isinstance(value, (list, tuple, set)):
        parts = [
            text
            for item in value
            if (text := provider_reason_text(item)) is not None
        ]
        return ", ".join(parts) if parts else None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text or text.casefold() in _GENERIC_REASON_VALUES:
        return None
    normalized = text.casefold()
    if any(marker in normalized for marker in _MODEL_CHATTER_MARKERS):
        return None
    return text[:300]


def extract_grs_violation_reason(value: object) -> str | None:
    found: list[str] = []
    seen: set[str] = set()

    def add(candidate: object) -> None:
        text = provider_reason_text(candidate)
        if text is None or text.casefold() in seen:
            return
        seen.add(text.casefold())
        found.append(text)

    def walk(item: object, depth: int) -> None:
        if depth > 5:
            return
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if _normalized_key(key) in _REASON_KEYS:
                    if isinstance(nested, (Mapping, list, tuple)):
                        walk(nested, depth + 1)
                    else:
                        add(nested)
            for nested in item.values():
                if isinstance(nested, (Mapping, list, tuple)):
                    walk(nested, depth + 1)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                walk(nested, depth + 1)

    walk(value, 0)
    return "; ".join(found)[:600] if found else None


def is_grs_violation_status(value: object) -> bool:
    return str(value or "").strip().casefold() in _GRS_VIOLATION_STATUSES


def is_grs_violation_record(record: object) -> bool:
    task_id = str(getattr(record, "task_id", "") or "")
    if not task_id.startswith("grs:"):
        return False
    raw = getattr(record, "raw", {})
    if isinstance(raw, Mapping) and is_grs_violation_status(raw.get("status")):
        return True
    details = " ".join(
        str(value or "")
        for value in (
            getattr(record, "failure_code", None),
            getattr(record, "failure_message", None),
            raw.get("code") if isinstance(raw, Mapping) else None,
            raw.get("message") if isinstance(raw, Mapping) else None,
            raw.get("msg") if isinstance(raw, Mapping) else None,
            raw.get("error") if isinstance(raw, Mapping) else None,
        )
    ).casefold()
    return "violation" in details or "moderation" in details


def is_grs_violation_error(error: BaseException) -> bool:
    return is_grs_violation_record(getattr(error, "record", None))


def grs_violation_reason(error: BaseException) -> str | None:
    record = getattr(error, "record", None)
    raw = getattr(record, "raw", {})
    reason = extract_grs_violation_reason(raw)
    return reason or provider_reason_text(getattr(record, "failure_message", None))


def with_image_output_guard(request: "KieGenerationRequest") -> "KieGenerationRequest":
    if request.model.provider_name != MediaProviderName.GRS.value:
        return request
    if _IMAGE_OUTPUT_GUARD.casefold() in request.provider_prompt.casefold():
        return request
    return replace(
        request,
        prompt=f"{request.provider_prompt}\n\n{_IMAGE_OUTPUT_GUARD}",
    )


def grs_retry_stage(
    *,
    provider_attempt: int,
    max_attempts: int,
    reason_text: str,
) -> str:
    attempt = max(1, int(provider_attempt))
    limit = max(attempt, int(max_attempts))
    return (
        f"Сервис генерации отклонил попытку {attempt}/{limit}. "
        f"{reason_text} Следующая последовательная попытка запускается сразу."
    )


def grs_terminal_stage(
    *,
    provider_attempt: int,
    max_attempts: int,
    reason_text: str,
) -> str:
    attempt = max(1, int(provider_attempt))
    limit = max(attempt, int(max_attempts))
    return (
        f"Сервис генерации отклонил попытку {attempt}/{limit}. "
        f"{reason_text} Лимит последовательной кампании исчерпан."
    )


__all__ = (
    "MediaProviderAdapter",
    "MediaProviderName",
    "MediaProviderRegistry",
    "MediaProviderUsage",
    "ProviderFailureKind",
    "ProviderRoute",
    "extract_grs_violation_reason",
    "extract_provider_credits",
    "grs_retry_stage",
    "grs_terminal_stage",
    "grs_violation_reason",
    "is_grs_violation_error",
    "is_grs_violation_record",
    "is_grs_violation_status",
    "provider_reason_text",
    "with_image_output_guard",
)
