from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html import escape
from typing import Any, Mapping

from aiogram.types import BufferedInputFile

from velvet_bot.domains.ai_usage import AITask
from velvet_bot.domains.media_generation.file_delivery_worker import _result_filename
from velvet_bot.domains.media_generation.friendly_worker import FriendlyKieGenerationWorker
from velvet_bot.domains.media_generation.models import KieGenerationRequest, KieTaskRecord

logger = logging.getLogger(__name__)
_INSTALLED = False
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
class _ReceiptContext:
    task: AITask
    request: KieGenerationRequest
    started_monotonic: float
    provider_started_monotonic: float | None = None
    provider_attempt: int | None = None
    max_attempts: int = 1
    provider_task_id: str | None = None


@dataclass(frozen=True, slots=True)
class _CostInfo:
    credits: Decimal | None
    usd: Decimal
    rub: Decimal
    source: str
    approximate: bool


@dataclass(frozen=True, slots=True)
class _DeliveryStats:
    preview_status: str
    original_status: str
    result_count: int
    result_bytes: int
    delivery_elapsed_ms: int
    errors: tuple[str, ...]


_ORIGINAL_START_PROGRESS = FriendlyKieGenerationWorker._start_progress
_ORIGINAL_PUBLISH_PROGRESS = FriendlyKieGenerationWorker._publish_progress


def _worker_contexts(
    worker: FriendlyKieGenerationWorker,
) -> tuple[dict[str, _ReceiptContext], dict[str, _ReceiptContext]]:
    by_queue = getattr(worker, "_media_receipt_by_queue", None)
    if not isinstance(by_queue, dict):
        by_queue = {}
        setattr(worker, "_media_receipt_by_queue", by_queue)
    by_provider = getattr(worker, "_media_receipt_by_provider", None)
    if not isinstance(by_provider, dict):
        by_provider = {}
        setattr(worker, "_media_receipt_by_provider", by_provider)
    return by_queue, by_provider


async def _start_progress_with_receipt(
    self: FriendlyKieGenerationWorker,
    *,
    task: AITask,
    request: KieGenerationRequest,
):
    by_queue, _ = _worker_contexts(self)
    by_queue[str(task.id)] = _ReceiptContext(
        task=task,
        request=request,
        started_monotonic=time.monotonic(),
        max_attempts=max(1, int(task.max_attempts)),
    )
    return await _ORIGINAL_START_PROGRESS(self, task=task, request=request)


async def _publish_progress_with_receipt(
    self: FriendlyKieGenerationWorker,
    progress,
    *,
    task: AITask,
    request: KieGenerationRequest,
    percent: int,
    stage: str,
    force: bool = False,
) -> None:
    by_queue, by_provider = _worker_contexts(self)
    context = by_queue.get(str(task.id))
    if context is None:
        context = _ReceiptContext(
            task=task,
            request=request,
            started_monotonic=time.monotonic(),
            max_attempts=max(1, int(task.max_attempts)),
        )
        by_queue[str(task.id)] = context

    attempt = _extract_attempt(stage)
    if attempt is not None:
        context.provider_attempt, context.max_attempts = attempt

    provider_task_id = _extract_provider_task_id(stage)
    if provider_task_id is not None:
        context.provider_task_id = provider_task_id
        context.provider_started_monotonic = (
            context.provider_started_monotonic or time.monotonic()
        )
        by_provider[provider_task_id] = context

    await _ORIGINAL_PUBLISH_PROGRESS(
        self,
        progress,
        task=task,
        request=request,
        percent=percent,
        stage=stage,
        force=force,
    )


def _extract_attempt(stage: object) -> tuple[int, int] | None:
    match = _ATTEMPT_RE.search(str(stage or ""))
    if match is None:
        return None
    attempt = max(1, int(match.group(1)))
    maximum = max(attempt, int(match.group(2)))
    return attempt, maximum


def _extract_provider_task_id(stage: object) -> str | None:
    text = str(stage or "").strip().rstrip(".")
    lowered = text.casefold()
    if not any(marker in lowered for marker in ("принял", "polling", "задач")):
        return None
    candidate = text.rsplit(" ", 1)[-1].strip().rstrip(".")
    if _PROVIDER_ID_RE.fullmatch(candidate) is None:
        return None
    return candidate


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def _env_decimal(name: str, default: str = "0") -> Decimal:
    return _decimal(os.getenv(name, default)) or Decimal("0")


def _extract_consumed_credits(value: object, *, depth: int = 0) -> Decimal | None:
    if depth > 6:
        return None
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _normalized_key(key) in _CONSUMED_CREDIT_KEYS:
                parsed = _decimal(item)
                if parsed is not None:
                    return parsed
        for item in value.values():
            if isinstance(item, (Mapping, list, tuple)):
                parsed = _extract_consumed_credits(item, depth=depth + 1)
                if parsed is not None:
                    return parsed
    elif isinstance(value, (list, tuple)):
        for item in value:
            parsed = _extract_consumed_credits(item, depth=depth + 1)
            if parsed is not None:
                return parsed
    return None


def _parse_datetime(value: object) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        numeric = _decimal(text)
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


def _provider_latency_ms(
    record: KieTaskRecord,
    context: _ReceiptContext | None = None,
) -> int | None:
    raw = record.raw if isinstance(record.raw, Mapping) else {}
    for key in ("costTime", "cost_time", "durationMs", "duration_ms"):
        value = _decimal(raw.get(key))
        if value is not None:
            return max(0, int(value))

    created = None
    completed = None
    for key in ("createTime", "createdAt", "create_time"):
        created = _parse_datetime(raw.get(key))
        if created is not None:
            break
    for key in ("completeTime", "completedAt", "complete_time"):
        completed = _parse_datetime(raw.get(key))
        if completed is not None:
            break
    if created is not None and completed is not None and completed >= created:
        return int((completed - created).total_seconds() * 1000)
    if context is not None and context.provider_started_monotonic is not None:
        return max(0, int((time.monotonic() - context.provider_started_monotonic) * 1000))
    return None


def _total_elapsed_ms(context: _ReceiptContext | None) -> int | None:
    if context is None:
        return None
    created_at = context.task.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    elapsed = datetime.now(timezone.utc) - created_at.astimezone(timezone.utc)
    return max(0, int(elapsed.total_seconds() * 1000))


async def _resolve_cost(
    worker: FriendlyKieGenerationWorker,
    request: KieGenerationRequest,
    record: KieTaskRecord,
    context: _ReceiptContext | None,
) -> _CostInfo:
    credits = Decimal(max(0, int(record.consumed_credits)))
    if credits <= 0:
        credits = _extract_consumed_credits(record.raw) or Decimal("0")

    if request.model.is_grs and credits <= 0 and context is not None:
        before = worker._provider_balances.get(str(context.task.id))
        if before is not None:
            try:
                after = await worker._client.get_grs_credits()
            except Exception:
                logger.warning("Could not read GRS balance after task %s", record.task_id)
            else:
                credits = max(Decimal("0"), before - after)

    estimated_usd = worker._pricing.estimate_usd(request)
    estimated_rub = worker._pricing.estimate_rub(
        request,
        usd_to_rub=worker._usd_to_rub,
    )

    if request.model.is_grs:
        credit_usd = _env_decimal("GRS_CREDIT_USD")
        if credits > 0 and credit_usd > 0:
            usd = credits * credit_usd
            return _CostInfo(
                credits=credits,
                usd=usd,
                rub=usd * worker._usd_to_rub,
                source="provider_credits",
                approximate=False,
            )
        if credits > 0:
            expected = {
                "nano_banana_2": Decimal("1200"),
                "nano_banana_pro": Decimal("1800"),
            }.get(request.model.value)
            if expected and expected > 0:
                usd = estimated_usd * credits / expected
                return _CostInfo(
                    credits=credits,
                    usd=usd,
                    rub=usd * worker._usd_to_rub,
                    source="balance_delta_estimated_rate",
                    approximate=True,
                )
        return _CostInfo(
            credits=credits if credits > 0 else None,
            usd=estimated_usd,
            rub=estimated_rub,
            source="estimate",
            approximate=True,
        )

    credit_usd = _env_decimal("KIE_CREDIT_USD", "0.005")
    if credits > 0 and credit_usd > 0:
        usd = credits * credit_usd
        return _CostInfo(
            credits=credits,
            usd=usd,
            rub=usd * worker._usd_to_rub,
            source="provider_credits",
            approximate=False,
        )
    return _CostInfo(
        credits=credits if credits > 0 else None,
        usd=estimated_usd,
        rub=estimated_rub,
        source="estimate",
        approximate=True,
    )


async def _send_original(
    worker: FriendlyKieGenerationWorker,
    *,
    chat_id: int,
    payload: bytes,
    filename: str,
    caption: str,
    video: bool,
) -> None:
    kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        "document": BufferedInputFile(payload, filename=filename),
        "caption": caption,
    }
    if video:
        kwargs["disable_content_type_detection"] = True
    await worker._send_telegram_with_retry(
        "original media document",
        lambda: worker._bot.send_document(**kwargs),
    )


async def _send_preview(
    worker: FriendlyKieGenerationWorker,
    *,
    chat_id: int,
    payload: bytes,
    filename: str,
    caption: str,
    video: bool,
) -> None:
    if video:
        await worker._send_telegram_with_retry(
            "video preview",
            lambda: worker._bot.send_video(
                chat_id,
                video=BufferedInputFile(payload, filename=filename),
                caption=caption,
                supports_streaming=True,
            ),
        )
        return
    await worker._send_telegram_with_retry(
        "image preview",
        lambda: worker._bot.send_photo(
            chat_id,
            photo=BufferedInputFile(payload, filename=filename),
            caption=caption,
        ),
    )


async def _deliver_with_receipt(
    self: FriendlyKieGenerationWorker,
    *,
    chat_id: int | None,
    request: KieGenerationRequest,
    record: KieTaskRecord,
) -> None:
    if chat_id is None:
        return

    delivery_started = time.monotonic()
    by_queue, by_provider = _worker_contexts(self)
    context = by_provider.get(record.task_id)
    if context is None:
        candidates = [
            item
            for item in by_queue.values()
            if item.request.model is request.model
            and int(item.task.payload.get("chat_id") or 0) == chat_id
        ]
        context = max(candidates, key=lambda item: item.started_monotonic, default=None)

    provider = "GRS AI" if request.model.is_grs else "Kie.ai"
    original_results: list[bool] = []
    preview_results: list[bool] = []
    errors: list[str] = []
    result_bytes = 0

    if not record.result_urls:
        errors.append(f"{provider} завершил задачу без URL результата.")
    else:
        for index, url in enumerate(record.result_urls, start=1):
            try:
                downloaded = await self._download_result(url)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                errors.append(f"Результат {index}: не удалось скачать оригинал: {error}")
                original_results.append(False)
                preview_results.append(False)
                continue

            result_bytes += len(downloaded.payload)
            filename = _result_filename(
                url=url,
                provider_task_id=record.task_id,
                index=index,
                mime_type=downloaded.mime_type,
                video=request.model.is_video,
            )
            media_name = "видеофайл" if request.model.is_video else "файл изображения"
            try:
                await _send_original(
                    self,
                    chat_id=chat_id,
                    payload=downloaded.payload,
                    filename=filename,
                    caption=f"Оригинальный {media_name} · {request.model.display_name}",
                    video=request.model.is_video,
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.exception("Original media delivery failed task=%s", record.task_id)
                errors.append(f"Результат {index}: оригинальный файл не отправлен: {error}")
                original_results.append(False)
            else:
                original_results.append(True)

            try:
                await _send_preview(
                    self,
                    chat_id=chat_id,
                    payload=downloaded.payload,
                    filename=filename,
                    caption=f"Предпросмотр · {request.model.display_name}",
                    video=request.model.is_video,
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.exception("Media preview delivery failed task=%s", record.task_id)
                errors.append(f"Результат {index}: предпросмотр не отправлен: {error}")
                preview_results.append(False)
            else:
                preview_results.append(True)

    original_status = _aggregate_delivery_status(original_results)
    preview_status = _aggregate_delivery_status(preview_results)
    delivery_stats = _DeliveryStats(
        preview_status=preview_status,
        original_status=original_status,
        result_count=len(record.result_urls),
        result_bytes=result_bytes,
        delivery_elapsed_ms=max(0, int((time.monotonic() - delivery_started) * 1000)),
        errors=tuple(errors),
    )
    cost = await _resolve_cost(self, request, record, context)
    provider_latency_ms = _provider_latency_ms(record, context)
    total_elapsed_ms = _total_elapsed_ms(context)
    receipt = _render_receipt(
        request=request,
        record=record,
        provider=provider,
        context=context,
        cost=cost,
        provider_latency_ms=provider_latency_ms,
        total_elapsed_ms=total_elapsed_ms,
        delivery=delivery_stats,
    )
    try:
        await self._send_telegram_with_retry(
            "generation receipt",
            lambda: self._bot.send_message(chat_id, receipt),
        )
    except Exception:
        logger.exception("Could not send generation receipt task=%s", record.task_id)

    if errors:
        warning = (
            "<b>Часть результата не доставлена</b>\n\n"
            + "\n".join(f"• {escape(item[:500])}" for item in errors)
            + f"\n\nЗадача провайдера: <code>{escape(record.task_id)}</code>"
        )
        try:
            await self._send_telegram_with_retry(
                "delivery warning",
                lambda: self._bot.send_message(chat_id, warning),
            )
        except Exception:
            logger.exception("Could not report delivery failure task=%s", record.task_id)

    await _persist_receipt_stats(
        self,
        context=context,
        request=request,
        record=record,
        cost=cost,
        provider_latency_ms=provider_latency_ms,
        total_elapsed_ms=total_elapsed_ms,
        delivery=delivery_stats,
    )

    if context is not None:
        by_queue.pop(str(context.task.id), None)
        self._provider_balances.pop(str(context.task.id), None)
    by_provider.pop(record.task_id, None)


def _aggregate_delivery_status(values: list[bool]) -> str:
    if not values:
        return "not_sent"
    if all(values):
        return "sent"
    if any(values):
        return "partial"
    return "failed"


def _format_decimal(value: Decimal) -> str:
    return format(value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP), "f")


def _format_credits(value: Decimal) -> str:
    rounded = value.quantize(_CREDIT_QUANTUM, rounding=ROUND_HALF_UP)
    text = format(rounded, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _duration_text(milliseconds: int | None) -> str:
    if milliseconds is None:
        return "нет данных"
    seconds = max(0, round(milliseconds / 1000))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} ч")
    if minutes:
        parts.append(f"{minutes} мин")
    parts.append(f"{seconds} сек")
    return " ".join(parts)


def _status_text(value: str) -> str:
    return {
        "sent": "отправлен",
        "partial": "отправлен частично",
        "failed": "ошибка",
        "not_sent": "не отправлен",
    }.get(value, value)


def _render_receipt(
    *,
    request: KieGenerationRequest,
    record: KieTaskRecord,
    provider: str,
    context: _ReceiptContext | None,
    cost: _CostInfo,
    provider_latency_ms: int | None,
    total_elapsed_ms: int | None,
    delivery: _DeliveryStats,
) -> str:
    attempt = context.provider_attempt if context and context.provider_attempt else 1
    maximum = context.max_attempts if context else 1
    prefix = "≈ " if cost.approximate else ""
    finance: list[str] = []
    if cost.credits is not None:
        finance.append(f"Списано: <b>{_format_credits(cost.credits)} кредитов</b>")
    finance.append(
        f"Стоимость: <b>{prefix}${_format_decimal(cost.usd)} · "
        f"{prefix}{_format_decimal(cost.rub)} ₽</b>"
    )
    return (
        f"<b>Ауф · {escape(request.model.display_name)}</b>\n"
        f"Провайдер: <b>{provider}</b>\n"
        f"Качество: <b>{escape(request.resolution)}</b>\n"
        f"Референсов: <b>{len(request.references)}</b>\n\n"
        + "\n".join(finance)
        + "\n"
        f"Генерация у провайдера: <b>{_duration_text(provider_latency_ms)}</b>\n"
        f"Всего с постановки в очередь: <b>{_duration_text(total_elapsed_ms)}</b>\n"
        f"Успешная попытка: <b>{attempt}/{maximum}</b>\n\n"
        f"Предпросмотр: <b>{_status_text(delivery.preview_status)}</b>\n"
        f"Оригинальный файл: <b>{_status_text(delivery.original_status)}</b>\n"
        f"Задача провайдера: <code>{escape(record.task_id)}</code>"
    )


async def _persist_receipt_stats(
    worker: FriendlyKieGenerationWorker,
    *,
    context: _ReceiptContext | None,
    request: KieGenerationRequest,
    record: KieTaskRecord,
    cost: _CostInfo,
    provider_latency_ms: int | None,
    total_elapsed_ms: int | None,
    delivery: _DeliveryStats,
) -> None:
    if context is None:
        return
    queue = getattr(worker, "_campaign_queue", None) or getattr(worker, "_queue", None)
    database = getattr(queue, "_database", None)
    if database is None:
        return

    stats = {
        "provider": "grs" if request.model.is_grs else "kie",
        "provider_model": worker._client.models.provider_model_for_request(request),
        "model_alias": request.model.value,
        "media_type": "video" if request.model.is_video else "photo",
        "resolution": request.resolution,
        "duration_seconds": request.duration_seconds if request.model.is_video else None,
        "reference_count": len(request.references),
        "content_mode": request.content_mode.value,
        "provider_task_id": record.task_id,
        "provider_attempt_count": context.provider_attempt or 1,
        "queue_attempt_count": context.task.attempt_count,
        "credits_consumed": str(cost.credits) if cost.credits is not None else None,
        "actual_cost_usd": str(cost.usd),
        "actual_cost_rub": str(cost.rub),
        "cost_source": cost.source,
        "cost_approximate": cost.approximate,
        "provider_latency_ms": provider_latency_ms,
        "total_elapsed_ms": total_elapsed_ms,
        "delivery_elapsed_ms": delivery.delivery_elapsed_ms,
        "result_count": delivery.result_count,
        "result_bytes": delivery.result_bytes,
        "preview_delivery_status": delivery.preview_status,
        "original_delivery_status": delivery.original_status,
        "delivery_errors": list(delivery.errors),
        "delivered_at": datetime.now(timezone.utc).isoformat(),
    }
    encoded = json.dumps({"media_receipt": stats}, ensure_ascii=False, default=str)
    usage_metadata = json.dumps(stats, ensure_ascii=False, default=str)
    try:
        async with database.acquire() as connection:
            await connection.execute(
                """UPDATE ai_tasks
                   SET result=result || $2::JSONB,updated_at=NOW()
                   WHERE id=$1::UUID""",
                context.task.id,
                encoded,
            )
            await connection.execute(
                """UPDATE ai_usage_events
                   SET actual_cost_rub=$2::NUMERIC,
                       latency_ms=COALESCE($3::BIGINT,latency_ms),
                       metadata=metadata || $4::JSONB
                   WHERE id=(
                       SELECT id FROM ai_usage_events
                       WHERE metadata->>'queue_task_id'=$1
                         AND status='success'
                       ORDER BY completed_at DESC NULLS LAST,id DESC
                       LIMIT 1
                   )""",
                str(context.task.id),
                cost.rub,
                provider_latency_ms,
                usage_metadata,
            )
    except Exception:
        logger.exception("Could not persist media receipt stats task=%s", context.task.id)


def install_media_generation_receipts() -> None:
    """Install provider receipts and reliable preview/original delivery."""

    global _INSTALLED
    if _INSTALLED:
        return
    FriendlyKieGenerationWorker._start_progress = _start_progress_with_receipt
    FriendlyKieGenerationWorker._publish_progress = _publish_progress_with_receipt
    FriendlyKieGenerationWorker._deliver_best_effort = _deliver_with_receipt
    _INSTALLED = True


__all__ = ("install_media_generation_receipts",)
