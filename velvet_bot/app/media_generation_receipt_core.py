from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html import escape
from typing import Mapping

from velvet_bot.domains.ai_usage import AITask
from velvet_bot.domains.media_generation.friendly_worker import FriendlyKieGenerationWorker
from velvet_bot.domains.media_generation.models import KieGenerationRequest, KieTaskRecord
from velvet_bot.infrastructure.ai import KieError

_MONEY_QUANTUM = Decimal("0.01")
_CREDIT_QUANTUM = Decimal("0.01")
_PROVIDER_ID_RE = re.compile(r"(?:grs:)?[A-Za-z0-9][A-Za-z0-9:_-]{7,}")
_ATTEMPT_RE = re.compile(r"попыт\w*\s+(\d+)\s*/\s*(\d+)", re.IGNORECASE)
_CONSUMED_CREDIT_KEYS = frozenset(
    {
        "creditsconsumed",
        "consumecredits",
        "consumedcredits",
        "usedcredits",
        "creditsused",
        "costcredits",
        "chargedcredits",
        "deductedcredits",
    }
)


@dataclass(slots=True)
class ReceiptContext:
    task: AITask
    request: KieGenerationRequest
    started_monotonic: float
    provider_started_monotonic: float | None = None
    provider_attempt: int | None = None
    max_attempts: int = 1
    provider_task_id: str | None = None


@dataclass(frozen=True, slots=True)
class CostInfo:
    credits: Decimal | None
    usd: Decimal
    rub: Decimal
    source: str
    approximate: bool


@dataclass(frozen=True, slots=True)
class DeliveryStats:
    preview_status: str
    original_status: str
    result_count: int
    result_bytes: int
    delivery_elapsed_ms: int
    errors: tuple[str, ...]


def extract_attempt(stage: object) -> tuple[int, int] | None:
    match = _ATTEMPT_RE.search(str(stage or ""))
    if match is None:
        return None
    attempt = max(1, int(match.group(1)))
    maximum = max(attempt, int(match.group(2)))
    return attempt, maximum


def extract_provider_task_id(stage: object) -> str | None:
    text = str(stage or "").strip().rstrip(".")
    lowered = text.casefold()
    if not any(marker in lowered for marker in ("принял", "polling", "задач")):
        return None
    candidate = text.rsplit(" ", 1)[-1].strip().rstrip(".")
    return candidate if _PROVIDER_ID_RE.fullmatch(candidate) else None


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def decimal_value(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def env_decimal(name: str, default: str = "0") -> Decimal:
    return decimal_value(os.getenv(name, default)) or Decimal("0")


def extract_consumed_credits(value: object, *, depth: int = 0) -> Decimal | None:
    if depth > 6:
        return None
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _normalized_key(key) in _CONSUMED_CREDIT_KEYS:
                parsed = decimal_value(item)
                if parsed is not None:
                    return parsed
        for item in value.values():
            if isinstance(item, (Mapping, list, tuple)):
                parsed = extract_consumed_credits(item, depth=depth + 1)
                if parsed is not None:
                    return parsed
    elif isinstance(value, (list, tuple)):
        for item in value:
            parsed = extract_consumed_credits(item, depth=depth + 1)
            if parsed is not None:
                return parsed
    return None


def parse_datetime(value: object) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        numeric = decimal_value(text)
        if numeric is not None:
            seconds = float(numeric)
            if seconds > 10_000_000_000:
                seconds /= 1000.0
            try:
                return datetime.fromtimestamp(seconds, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def provider_latency_ms(
    record: KieTaskRecord,
    context: ReceiptContext | None = None,
) -> int | None:
    raw = record.raw if isinstance(record.raw, Mapping) else {}
    for key in ("costTime", "cost_time", "durationMs", "duration_ms"):
        value = decimal_value(raw.get(key))
        if value is not None:
            return max(0, int(value))
    created = next(
        (parsed for key in ("createTime", "createdAt", "create_time")
         if (parsed := parse_datetime(raw.get(key))) is not None),
        None,
    )
    completed = next(
        (parsed for key in ("completeTime", "completedAt", "complete_time")
         if (parsed := parse_datetime(raw.get(key))) is not None),
        None,
    )
    if created is not None and completed is not None and completed >= created:
        return int((completed - created).total_seconds() * 1000)
    if context is not None and context.provider_started_monotonic is not None:
        return max(0, int((time.monotonic() - context.provider_started_monotonic) * 1000))
    return None


def total_elapsed_ms(context: ReceiptContext | None) -> int | None:
    if context is None:
        return None
    created_at = context.task.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    elapsed = datetime.now(timezone.utc) - created_at.astimezone(timezone.utc)
    return max(0, int(elapsed.total_seconds() * 1000))


async def resolve_cost(
    worker: FriendlyKieGenerationWorker,
    request: KieGenerationRequest,
    record: KieTaskRecord,
    context: ReceiptContext | None,
) -> CostInfo:
    credits = Decimal(max(0, int(record.consumed_credits)))
    if credits <= 0:
        credits = extract_consumed_credits(record.raw) or Decimal("0")
    if request.model.is_grs and credits <= 0 and context is not None:
        before = worker._provider_balances.get(str(context.task.id))
        if before is not None:
            try:
                after = await worker._client.get_grs_credits()
            except KieError:
                after = None
            if after is not None:
                credits = max(Decimal("0"), before - after)

    estimated_usd = worker._pricing.estimate_usd(request)
    estimated_rub = worker._pricing.estimate_rub(request, usd_to_rub=worker._usd_to_rub)
    if request.model.is_grs:
        credit_usd = env_decimal("GRS_CREDIT_USD")
        if credits > 0 and credit_usd > 0:
            usd = credits * credit_usd
            return CostInfo(credits, usd, usd * worker._usd_to_rub, "provider_credits", False)
        expected = {
            "nano_banana_2": Decimal("1200"),
            "nano_banana_pro": Decimal("1800"),
        }.get(request.model.value)
        if credits > 0 and expected:
            usd = estimated_usd * credits / expected
            return CostInfo(credits, usd, usd * worker._usd_to_rub, "balance_delta_estimated_rate", True)
        return CostInfo(credits if credits > 0 else None, estimated_usd, estimated_rub, "estimate", True)

    credit_usd = env_decimal("KIE_CREDIT_USD", "0.005")
    if credits > 0 and credit_usd > 0:
        usd = credits * credit_usd
        return CostInfo(credits, usd, usd * worker._usd_to_rub, "provider_credits", False)
    return CostInfo(credits if credits > 0 else None, estimated_usd, estimated_rub, "estimate", True)


def aggregate_delivery_status(values: list[bool]) -> str:
    if not values:
        return "not_sent"
    if all(values):
        return "sent"
    return "partial" if any(values) else "failed"


def format_decimal(value: Decimal) -> str:
    return format(value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP), "f")


def format_credits(value: Decimal) -> str:
    text = format(value.quantize(_CREDIT_QUANTUM, rounding=ROUND_HALF_UP), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def duration_text(milliseconds: int | None) -> str:
    if milliseconds is None:
        return "нет данных"
    seconds = max(0, round(milliseconds / 1000))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts = ([f"{hours} ч"] if hours else []) + ([f"{minutes} мин"] if minutes else [])
    return " ".join([*parts, f"{seconds} сек"])


def _status_text(value: str) -> str:
    return {
        "sent": "отправлен",
        "partial": "отправлен частично",
        "failed": "ошибка",
        "not_sent": "не отправлен",
    }.get(value, value)


def render_receipt(
    *,
    request: KieGenerationRequest,
    record: KieTaskRecord,
    provider: str,
    context: ReceiptContext | None,
    cost: CostInfo,
    provider_latency: int | None,
    total_elapsed: int | None,
    delivery: DeliveryStats,
) -> str:
    attempt = context.provider_attempt if context and context.provider_attempt else 1
    maximum = context.max_attempts if context else 1
    prefix = "≈ " if cost.approximate else ""
    finance = []
    if cost.credits is not None:
        finance.append(f"Списано: <b>{format_credits(cost.credits)} кредитов</b>")
    finance.append(
        f"Стоимость: <b>{prefix}${format_decimal(cost.usd)} · "
        f"{prefix}{format_decimal(cost.rub)} ₽</b>"
    )
    return (
        f"<b>Ауф · {escape(request.model.display_name)}</b>\n"
        f"Провайдер: <b>{provider}</b>\n"
        f"Качество: <b>{escape(request.resolution)}</b>\n"
        f"Референсов: <b>{len(request.references)}</b>\n\n"
        + "\n".join(finance)
        + "\n"
        f"Генерация у провайдера: <b>{duration_text(provider_latency)}</b>\n"
        f"Всего с постановки в очередь: <b>{duration_text(total_elapsed)}</b>\n"
        f"Успешная попытка: <b>{attempt}/{maximum}</b>\n\n"
        f"Предпросмотр: <b>{_status_text(delivery.preview_status)}</b>\n"
        f"Оригинальный файл: <b>{_status_text(delivery.original_status)}</b>\n"
        f"Задача провайдера: <code>{escape(record.task_id)}</code>"
    )
