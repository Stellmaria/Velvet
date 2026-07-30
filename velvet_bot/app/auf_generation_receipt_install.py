from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Any
from uuid import UUID

from aiogram.exceptions import TelegramAPIError

from velvet_bot.application.media_tasks import task_payload_mapping, task_result_urls
from velvet_bot.application.workspace_tasks import get_owned_success_task
from velvet_bot.domains.auf_wallet import (
    AufInsufficientBalance,
    AufPriceNotConfigured,
    AufWalletFrozen,
    format_auf_units,
)
from velvet_bot.domains.media_generation import KIE_GENERATION_TASK_TYPE
from velvet_bot.domains.media_generation.models import (
    KieGenerationRequest,
    KieTaskRecord,
    KieTaskState,
)

logger = logging.getLogger(__name__)
_INSTALLED = False
_DELIVERY_ERRORS = (
    TelegramAPIError,
    RuntimeError,
    ValueError,
    OSError,
    TypeError,
    AttributeError,
)


@dataclass(frozen=True, slots=True)
class AufGenerationReceipt:
    task_id: UUID | None = None
    elapsed_seconds: int | None = None
    successful_attempt: int | None = None
    quoted_units: int = 0
    captured_units: int = 0
    charge_status: str = ""


def _row_value(row: Any, key: str, default: object = None) -> object:
    try:
        value = row[key]
    except (KeyError, TypeError, IndexError):
        return default
    return default if value is None else value


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(str(value or "0").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(str(value or "0").strip()))
    except (TypeError, ValueError):
        return 0


def _elapsed_seconds(created_at: object, completed_at: object) -> int | None:
    if not isinstance(created_at, datetime) or not isinstance(completed_at, datetime):
        return None
    created = created_at
    completed = completed_at
    if created.tzinfo is None and completed.tzinfo is not None:
        created = created.replace(tzinfo=completed.tzinfo)
    elif completed.tzinfo is None and created.tzinfo is not None:
        completed = completed.replace(tzinfo=created.tzinfo)
    try:
        return max(0, int((completed - created).total_seconds() + 0.5))
    except TypeError:
        return None


def receipt_from_task_row(row: Any) -> AufGenerationReceipt:
    payload = task_payload_mapping(_row_value(row, "payload", {}))
    result = task_payload_mapping(_row_value(row, "result", {}))
    attempt = (
        _positive_int(result.get("provider_attempt_count"))
        or _positive_int(result.get("successful_attempt"))
        or _positive_int(result.get("attempt_count"))
        or _positive_int(_row_value(row, "attempt_count"))
    )
    quoted_units = _non_negative_int(
        _row_value(
            row,
            "quoted_units",
            payload.get("auf_expected_quoted_units"),
        )
    )
    captured_units = _non_negative_int(_row_value(row, "captured_units", 0))
    charge_status = str(_row_value(row, "charge_status", "") or "").strip()
    if charge_status == "captured" and captured_units <= 0:
        captured_units = quoted_units
    task_id_value = _row_value(row, "id")
    task_id = task_id_value if isinstance(task_id_value, UUID) else None
    return AufGenerationReceipt(
        task_id=task_id,
        elapsed_seconds=_elapsed_seconds(
            _row_value(row, "created_at"),
            _row_value(row, "completed_at"),
        ),
        successful_attempt=attempt,
        quoted_units=quoted_units,
        captured_units=captured_units,
        charge_status=charge_status,
    )


def format_generation_elapsed(seconds: int | None) -> str:
    if seconds is None:
        return "не сохранено"
    safe = max(0, int(seconds))
    if safe < 1:
        return "менее 1 сек"
    hours, remainder = divmod(safe, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} ч")
    if minutes:
        parts.append(f"{minutes} мин")
    if secs or not parts:
        parts.append(f"{secs} сек")
    return " ".join(parts)


def build_public_result_caption(
    request: KieGenerationRequest,
    receipt: AufGenerationReceipt | None,
) -> str:
    media_name = "Видео" if request.model.is_video else "Изображение"
    lines = [
        f"<b>Ауф · {escape(request.model.display_name)}</b>",
        f"{media_name}: <b>готово</b>",
        f"Качество: <b>{escape(request.resolution)}</b>",
        f"Референсов: <b>{len(request.references)}</b>",
    ]
    if receipt is not None:
        lines.append(
            "Время генерации: "
            f"<b>{escape(format_generation_elapsed(receipt.elapsed_seconds))}</b>"
        )
        if receipt.successful_attempt is not None:
            lines.append(
                f"Успешная попытка: <b>{receipt.successful_attempt}</b>"
            )
        if receipt.charge_status == "captured":
            lines.append(
                f"Списано: <b>{format_auf_units(receipt.captured_units)}</b>"
            )
        elif receipt.quoted_units > 0:
            lines.append("Списание: <b>0 вельветов · служебная генерация</b>")
    return "\n".join(lines)


def _worker_database(worker: Any) -> Any | None:
    for queue_name in ("_campaign_queue", "_queue"):
        queue = getattr(worker, queue_name, None)
        database = getattr(queue, "_database", None)
        if database is not None:
            return database
        repository = getattr(queue, "_repository", None)
        database = getattr(repository, "_database", None)
        if database is not None:
            return database
    return None


async def _load_receipt_by_provider_task(
    worker: Any,
    provider_task_id: str,
) -> AufGenerationReceipt | None:
    database = _worker_database(worker)
    if database is None:
        return None
    async with database.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                task.id,
                task.payload,
                task.result,
                task.attempt_count,
                task.created_at,
                task.completed_at,
                charge.quoted_units,
                charge.captured_units,
                charge.status AS charge_status
            FROM ai_tasks AS task
            LEFT JOIN auf_task_charges AS charge ON charge.task_id = task.id
            WHERE task.task_type = $1::VARCHAR
              AND task.status = 'success'
              AND (
                    task.result ->> 'provider_task_id' = $2::TEXT
                    OR task.payload -> 'kie_campaign' ->> 'last_provider_task_id' = $2::TEXT
                  )
            ORDER BY task.completed_at DESC NULLS LAST, task.updated_at DESC
            LIMIT 1
            """,
            KIE_GENERATION_TASK_TYPE,
            str(provider_task_id),
        )
    return receipt_from_task_row(row) if row is not None else None


async def _safe_direct_fallback(
    *,
    recovery: Any,
    bot: Any,
    chat_id: int,
    request: KieGenerationRequest,
    url: str,
    caption: str | None,
) -> bool:
    fallback_caption = (
        (f"{caption}\n\n" if caption else "")
        + "Оригинал временно не скачался, поэтому результат отправлен напрямую."
    )
    try:
        if request.model.is_video:
            await recovery.send_bot_with_retry(
                "direct result video",
                lambda: bot.send_video(
                    chat_id,
                    video=url,
                    caption=fallback_caption,
                    supports_streaming=True,
                ),
            )
        else:
            await recovery.send_bot_with_retry(
                "direct result image",
                lambda: bot.send_photo(
                    chat_id,
                    photo=url,
                    caption=fallback_caption,
                ),
            )
        return True
    except asyncio.CancelledError:
        raise
    except _DELIVERY_ERRORS:
        logger.exception("Direct Auf result delivery failed")
        return False


async def _deliver_urls(
    *,
    recovery: Any,
    bot: Any,
    chat_id: int,
    request: KieGenerationRequest,
    record: KieTaskRecord,
    caption: str,
) -> int:
    delivered = 0
    for index, url in enumerate(record.result_urls, start=1):
        item_caption = caption if index == 1 else None
        try:
            downloaded = await asyncio.to_thread(
                recovery.download_result_http,
                url,
                timeout_seconds=recovery.RESULT_DOWNLOAD_TIMEOUT_SECONDS,
                max_bytes=recovery.RESULT_MAX_BYTES,
                user_agent=recovery.DEFAULT_RESULT_USER_AGENT,
            )
            document_sent, preview_sent = await recovery.send_downloaded_result(
                bot=bot,
                chat_id=chat_id,
                request=request,
                record=record,
                url=url,
                index=index,
                payload=downloaded.payload,
                mime_type=downloaded.mime_type,
                caption=item_caption,
            )
            if document_sent or preview_sent:
                delivered += 1
                continue
            raise RuntimeError("Telegram не принял ни оригинал, ни предпросмотр.")
        except asyncio.CancelledError:
            raise
        except _DELIVERY_ERRORS:
            logger.exception(
                "Auf result delivery failed provider_task=%s url=%s",
                record.task_id,
                url,
            )
            if await _safe_direct_fallback(
                recovery=recovery,
                bot=bot,
                chat_id=chat_id,
                request=request,
                url=url,
                caption=item_caption,
            ):
                delivered += 1
    return delivered


async def deliver_record_with_receipt(
    self: Any,
    *,
    chat_id: int | None,
    request: KieGenerationRequest,
    record: KieTaskRecord,
) -> None:
    if chat_id is None:
        return
    recovery = importlib.import_module("velvet_bot.app.auf_result_delivery_recovery")
    receipt = await _load_receipt_by_provider_task(self, record.task_id)
    caption = build_public_result_caption(request, receipt)
    logger.info(
        "Auf generation completed task=%s provider_task=%s elapsed_seconds=%s "
        "successful_attempt=%s charge_status=%s captured_units=%s",
        receipt.task_id if receipt else None,
        record.task_id,
        receipt.elapsed_seconds if receipt else None,
        receipt.successful_attempt if receipt else None,
        receipt.charge_status if receipt else "",
        receipt.captured_units if receipt else 0,
    )
    if not record.result_urls:
        await recovery.send_bot_with_retry(
            "empty result notice",
            lambda: self._bot.send_message(
                chat_id,
                caption
                + "\n\nРезультат готов, но файл пока недоступен для доставки. "
                "Откройте «Мои задачи» и повторите получение позже.",
            ),
        )
        return
    delivered = await _deliver_urls(
        recovery=recovery,
        bot=self._bot,
        chat_id=chat_id,
        request=request,
        record=record,
        caption=caption,
    )
    if delivered <= 0:
        await self._bot.send_message(
            chat_id,
            "Генерация завершена, но Telegram не принял файл. "
            "Результат сохранён в разделе «Мои задачи».",
        )


async def redeliver_user_task_with_receipt(
    callback: Any,
    *,
    database: Any,
    workspace_id: int,
    task_id_text: str,
) -> None:
    recovery = importlib.import_module("velvet_bot.app.auf_result_delivery_recovery")
    active = importlib.import_module("velvet_bot.app.auf_active_delivery_fix")
    try:
        task_id = UUID(task_id_text)
    except (TypeError, ValueError):
        await callback.answer("Некорректный ID задачи.", show_alert=True)
        return
    row = await get_owned_success_task(
        database,
        task_id=task_id,
        workspace_id=workspace_id,
        actor_user_id=callback.from_user.id,
    )
    if row is None:
        await callback.answer(
            "Готовая задача не найдена или принадлежит другому пользователю.",
            show_alert=True,
        )
        return
    payload = task_payload_mapping(row["payload"])
    request_payload = task_payload_mapping(payload.get("request"))
    try:
        request = KieGenerationRequest.from_task_payload(request_payload)
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
    result = task_payload_mapping(row["result"])
    urls = task_result_urls(result)
    provider_task_id = str(result.get("provider_task_id") or "").strip()
    if not urls:
        provider_task_id = active.provider_task_id(result, payload) or ""
        if not provider_task_id:
            await callback.answer(
                "У задачи не сохранился готовый файл. Новая генерация не запускалась.",
                show_alert=True,
            )
            return
        try:
            urls = await active._load_provider_urls(provider_task_id)
            await active._persist_provider_urls(
                database,
                task_id=task_id,
                provider_task_id_value=provider_task_id,
                urls=urls,
            )
        except asyncio.CancelledError:
            raise
        except _DELIVERY_ERRORS:
            logger.exception("Could not recover Auf task result task=%s", task_id)
            await callback.answer(
                "Не удалось получить сохранённый файл. Новая генерация не запускалась.",
                show_alert=True,
            )
            return
    record = KieTaskRecord(
        task_id=provider_task_id or str(task_id),
        state=KieTaskState.SUCCESS,
        result_urls=urls,
    )
    chat_id = (
        int(callback.message.chat.id)
        if getattr(callback, "message", None) is not None
        else int(callback.from_user.id)
    )
    await callback.answer("Повторяю доставку без новой генерации и списания.")
    receipt = receipt_from_task_row(row)
    caption = build_public_result_caption(request, receipt)
    delivered = await _deliver_urls(
        recovery=recovery,
        bot=callback.bot,
        chat_id=chat_id,
        request=request,
        record=record,
        caption=caption,
    )
    await callback.bot.send_message(
        chat_id,
        (
            f"Повторная доставка завершена: <b>{delivered}/{len(urls)}</b>. "
            "Новая генерация и новое списание не запускались."
            if delivered
            else "Не удалось повторно доставить сохранённый результат. "
            "Новая генерация и новое списание не запускались."
        ),
    )


def append_receipt_to_task_card(text: str, row: Any) -> str:
    if str(_row_value(row, "status", "")) != "success":
        return text
    receipt = receipt_from_task_row(row)
    lines = [
        f"Время генерации: <b>{escape(format_generation_elapsed(receipt.elapsed_seconds))}</b>"
    ]
    if receipt.successful_attempt is not None:
        lines.append(f"Успешная попытка: <b>{receipt.successful_attempt}</b>")
    addition = "\n".join(lines)
    marker = "\n\nНажмите"
    if marker in text:
        return text.replace(marker, f"\n{addition}{marker}", 1)
    return f"{text}\n{addition}"


def append_receipt_to_task_line(text: str, row: Any) -> str:
    if str(_row_value(row, "status", "")) != "success":
        return text
    receipt = receipt_from_task_row(row)
    details = [f"время {format_generation_elapsed(receipt.elapsed_seconds)}"]
    if receipt.successful_attempt is not None:
        details.append(f"попытка {receipt.successful_attempt}")
    return f"{text}\n  {escape(' · '.join(details))}"


def _install_photo_charge_guard() -> None:
    photo_ui = importlib.import_module("velvet_bot.app.auf_photo_ui_install")
    original = getattr(photo_ui, "_enqueue_auf_photo", None)
    if not callable(original) or getattr(original, "__auf_charge_guard__", False):
        return

    async def guarded(*args: Any, **kwargs: Any) -> None:
        callback = args[0] if args else kwargs.get("callback")
        try:
            await original(*args, **kwargs)
        except (
            AufInsufficientBalance,
            AufWalletFrozen,
            AufPriceNotConfigured,
            ValueError,
            RuntimeError,
        ) as error:
            if callback is None:
                raise
            await callback.answer(str(error), show_alert=True)

    guarded.__auf_charge_guard__ = True  # type: ignore[attr-defined]
    photo_ui._enqueue_auf_photo = guarded


def install_auf_generation_receipts() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    recovery = importlib.import_module("velvet_bot.app.auf_result_delivery_recovery")
    active = importlib.import_module("velvet_bot.app.auf_active_delivery_fix")
    portal = importlib.import_module("velvet_bot.app.auf_user_portal_install")
    workers = importlib.import_module("velvet_bot.app.workers")

    workers.KieGenerationWorker.install_delivery_handler(deliver_record_with_receipt)
    recovery.install_redelivery_handler(redeliver_user_task_with_receipt)

    original_card = active.task_card_text
    if not getattr(original_card, "__auf_receipt_wrapped__", False):
        def card_with_receipt(*, row: Any, offset: int) -> str:
            return append_receipt_to_task_card(
                original_card(row=row, offset=offset),
                row,
            )

        card_with_receipt.__auf_receipt_wrapped__ = True  # type: ignore[attr-defined]
        active.task_card_text = card_with_receipt

    original_line = portal.format_user_task_line
    if not getattr(original_line, "__auf_receipt_wrapped__", False):
        def line_with_receipt(row: Any) -> str:
            return append_receipt_to_task_line(original_line(row), row)

        line_with_receipt.__auf_receipt_wrapped__ = True  # type: ignore[attr-defined]
        portal.format_user_task_line = line_with_receipt

    _install_photo_charge_guard()
    _INSTALLED = True


__all__ = (
    "AufGenerationReceipt",
    "append_receipt_to_task_card",
    "append_receipt_to_task_line",
    "build_public_result_caption",
    "deliver_record_with_receipt",
    "format_generation_elapsed",
    "install_auf_generation_receipts",
    "receipt_from_task_row",
    "redeliver_user_task_with_receipt",
)
