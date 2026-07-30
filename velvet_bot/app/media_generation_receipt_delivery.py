from __future__ import annotations

import asyncio
import logging
import time
from html import escape
from typing import Any

from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile

from velvet_bot.domains.media_generation.file_delivery_worker import _result_filename
from velvet_bot.domains.media_generation.friendly_worker import FriendlyKieGenerationWorker
from velvet_bot.domains.media_generation.models import KieGenerationRequest, KieTaskRecord

from .media_generation_receipt_core import (
    DeliveryStats,
    ReceiptContext,
    aggregate_delivery_status,
    provider_latency_ms,
    render_receipt,
    resolve_cost,
    total_elapsed_ms,
)
from .media_generation_receipt_persistence import persist_receipt_stats

logger = logging.getLogger(__name__)
_DELIVERY_ERRORS = (TelegramAPIError, RuntimeError, ValueError, OSError)


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
    else:
        await worker._send_telegram_with_retry(
            "image preview",
            lambda: worker._bot.send_photo(
                chat_id,
                photo=BufferedInputFile(payload, filename=filename),
                caption=caption,
            ),
        )


def _find_context(
    worker: FriendlyKieGenerationWorker,
    *,
    chat_id: int,
    request: KieGenerationRequest,
    provider_task_id: str,
) -> ReceiptContext | None:
    by_provider = getattr(worker, "_media_receipt_by_provider", {})
    context = by_provider.get(provider_task_id)
    if context is not None:
        return context
    by_queue = getattr(worker, "_media_receipt_by_queue", {})
    candidates = [
        item for item in by_queue.values()
        if item.request.model is request.model
        and int(item.task.payload.get("chat_id") or 0) == chat_id
    ]
    return max(candidates, key=lambda item: item.started_monotonic, default=None)


async def deliver_with_receipt(
    self: FriendlyKieGenerationWorker,
    *,
    chat_id: int | None,
    request: KieGenerationRequest,
    record: KieTaskRecord,
) -> None:
    if chat_id is None:
        return
    started = time.monotonic()
    context = _find_context(
        self,
        chat_id=chat_id,
        request=request,
        provider_task_id=record.task_id,
    )
    provider = "GRS AI" if request.model.is_grs else "Kie.ai"
    originals: list[bool] = []
    previews: list[bool] = []
    errors: list[str] = []
    total_bytes = 0

    if not record.result_urls:
        errors.append(f"{provider} завершил задачу без URL результата.")
    for index, url in enumerate(record.result_urls, start=1):
        try:
            downloaded = await self._download_result(url)
        except asyncio.CancelledError:
            raise
        except (RuntimeError, ValueError, OSError) as error:
            errors.append(f"Результат {index}: не удалось скачать оригинал: {error}")
            originals.append(False)
            previews.append(False)
            continue

        total_bytes += len(downloaded.payload)
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
        except _DELIVERY_ERRORS as error:
            logger.exception("Original media delivery failed task=%s", record.task_id)
            errors.append(f"Результат {index}: оригинальный файл не отправлен: {error}")
            originals.append(False)
        else:
            originals.append(True)

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
        except _DELIVERY_ERRORS as error:
            logger.exception("Media preview delivery failed task=%s", record.task_id)
            errors.append(f"Результат {index}: предпросмотр не отправлен: {error}")
            previews.append(False)
        else:
            previews.append(True)

    delivery = DeliveryStats(
        preview_status=aggregate_delivery_status(previews),
        original_status=aggregate_delivery_status(originals),
        result_count=len(record.result_urls),
        result_bytes=total_bytes,
        delivery_elapsed_ms=max(0, int((time.monotonic() - started) * 1000)),
        errors=tuple(errors),
    )
    cost = await resolve_cost(self, request, record, context)
    provider_ms = provider_latency_ms(record, context)
    total_ms = total_elapsed_ms(context)
    receipt = render_receipt(
        request=request,
        record=record,
        provider=provider,
        context=context,
        cost=cost,
        provider_latency=provider_ms,
        total_elapsed=total_ms,
        delivery=delivery,
    )
    try:
        await self._send_telegram_with_retry(
            "generation receipt",
            lambda: self._bot.send_message(chat_id, receipt),
        )
    except _DELIVERY_ERRORS:
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
        except _DELIVERY_ERRORS:
            logger.exception("Could not report delivery failure task=%s", record.task_id)

    await persist_receipt_stats(
        self,
        context=context,
        request=request,
        record=record,
        cost=cost,
        provider_latency_ms=provider_ms,
        total_elapsed_ms=total_ms,
        delivery=delivery,
    )
    if context is not None:
        getattr(self, "_media_receipt_by_queue", {}).pop(str(context.task.id), None)
        self._provider_balances.pop(str(context.task.id), None)
    getattr(self, "_media_receipt_by_provider", {}).pop(record.task_id, None)
