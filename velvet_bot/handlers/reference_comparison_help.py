from __future__ import annotations

import asyncio
import io
import logging
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)
from aiogram.filters import BaseFilter
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.ai_job_runtime import AIJobTracker
from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.handlers.admin_directory import AdminDirectoryCallback
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.quality_ui import QualityCallback, quality_callback
from velvet_bot.reference_catalog import get_reference_page
from velvet_bot.reference_comparison import ReferenceComparisonClient
from velvet_bot.reference_comparison_reports import ReferenceComparisonReportRepository
from velvet_bot.reference_comparison_ui import format_reference_comparison_report
from velvet_bot.reference_ui import ReferenceCallback


router = Router(name=__name__)
logger = logging.getLogger(__name__)

_MARKER_RE = re.compile(r"VELVET_AI:COMPARE_REF:(\d+):(\d+):(\d+)")
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 90
_RETRY_DELAYS = (1.0, 3.0)


class ReferenceComparisonReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> dict[str, int] | bool:
        reply = message.reply_to_message
        if reply is None:
            return False
        source = reply.text or reply.caption or ""
        match = _MARKER_RE.search(source)
        if match is None:
            return False
        return {
            "reference_character_id": int(match.group(1)),
            "reference_id": int(match.group(2)),
            "reference_offset": int(match.group(3)),
        }


def _result_file(message: Message) -> tuple[str, str | None] | None:
    if message.photo:
        photo = message.photo[-1]
        return photo.file_id, photo.file_unique_id
    if message.document and (message.document.mime_type or "").startswith("image/"):
        return message.document.file_id, message.document.file_unique_id
    return None


async def _download_file(bot: Bot, file_id: str) -> bytes:
    errors: list[BaseException] = []
    for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
        try:
            destination = io.BytesIO()
            await bot.download(
                file_id,
                destination=destination,
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
                seek=True,
            )
            value = destination.getvalue()
            if value:
                return value
            errors.append(RuntimeError("Telegram вернул пустой файл."))
        except asyncio.CancelledError:
            raise
        except TelegramBadRequest as error:
            errors.append(error)
            break
        except (TelegramNetworkError, TimeoutError, ConnectionError, OSError) as error:
            errors.append(error)
            if attempt >= _DOWNLOAD_ATTEMPTS:
                break
            await asyncio.sleep(_RETRY_DELAYS[attempt - 1])
        except TelegramAPIError as error:
            errors.append(error)
            break
    if errors:
        raise RuntimeError(f"Не удалось скачать изображение: {errors[-1]}")
    raise RuntimeError("Telegram вернул пустой файл.")


@router.callback_query(QualityCallback.filter(F.action == "refcompare_start"))
async def handle_reference_compare_start(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👥 Выбрать персонажа",
                    callback_data=AdminDirectoryCallback(action="categories").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Velvet AI",
                    callback_data=quality_callback("ai_menu"),
                )
            ],
        ]
    )
    try:
        await callback.message.edit_text(
            "<b>🔎 Сравнение результата с референсом</b>\n\n"
            "Выберите персонажа, откройте его референсы и нажмите "
            "<b>«Сравнить результат»</b> на нужном референсе. Бот попросит "
            "готовое изображение отдельной подписанной формой. Slash-команда не нужна.",
            reply_markup=keyboard,
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise
    await callback.answer()


@router.callback_query(ReferenceCallback.filter(F.action == "compare_help"))
async def handle_reference_compare_help(
    callback: CallbackQuery,
    callback_data: ReferenceCallback,
    database: Database,
) -> None:
    page = await get_reference_page(
        database,
        callback_data.character_id,
        callback_data.offset,
    )
    if (
        page is None
        or page.reference is None
        or page.reference.id != callback_data.reference_id
    ):
        await callback.answer("Референс больше недоступен.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Форма доступна только в личном чате.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        "<b>🔎 Сравнение результата с референсом</b>\n\n"
        f"Персонаж: <b>{escape(page.character.name)}</b>\n"
        f"Референс: <b>{page.offset + 1}</b> из <b>{page.total}</b>\n\n"
        "Ответьте на это сообщение готовым изображением как фото или image-файлом. "
        "Qwen сравнит лицо, волосы, телосложение и уникальные видимые признаки.\n\n"
        f"<code>VELVET_AI:COMPARE_REF:{page.character.id}:"
        f"{page.reference.id}:{page.offset}</code>",
        reply_markup=ForceReply(selective=True),
    )


@router.message(ReferenceComparisonReplyFilter())
async def handle_reference_comparison_reply(
    message: Message,
    reference_character_id: int,
    reference_id: int,
    reference_offset: int,
    database: Database,
    bot: Bot,
) -> None:
    result_file = _result_file(message)
    if result_file is None:
        await message.answer("Нужно ответить фотографией или image-документом.")
        return
    page = await get_reference_page(database, reference_character_id, reference_offset)
    if page is None or page.reference is None or page.reference.id != reference_id:
        await message.answer("Выбранный референс больше недоступен.")
        return
    settings = load_settings()
    if not settings.ai_vision_enabled:
        await message.answer("Qwen отключён в настройках бота.")
        return
    result_file_id, result_unique_id = result_file
    tracker = await AIJobTracker.create(
        database=database,
        source_message=message,
        kind="reference_comparison",
        title=f"Сравнение с референсом · {page.character.name}",
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        request_payload={
            "character_id": page.character.id,
            "reference_id": page.reference.id,
            "reference_index": page.offset + 1,
            "result_file_id": result_file_id,
            "result_file_unique_id": result_unique_id,
        },
    )
    try:
        await tracker.stage("downloading")
        reference_bytes, result_bytes = await asyncio.gather(
            _download_file(bot, page.reference.telegram_file_id),
            _download_file(bot, result_file_id),
        )
        client = ReferenceComparisonClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        await tracker.stage("analyzing")
        async with get_local_ai_lock():
            report = await client.compare(reference_bytes, result_bytes)
        await tracker.stage("saving")
        report_id = await ReferenceComparisonReportRepository(database).save(
            character_id=page.character.id,
            reference_id=page.reference.id,
            result_file_id=result_file_id,
            result_file_unique_id=result_unique_id,
            provider=client.provider,
            model=client.model,
            report=report,
            created_by=message.from_user.id if message.from_user else None,
        )
        rendered = format_reference_comparison_report(
            report_id=report_id,
            character_name=page.character.name,
            reference_index=page.offset + 1,
            reference_total=page.total,
            report=report,
        )
        await tracker.ready(
            result_text=rendered,
            result_payload=report,
            reference_type="reference_comparison_report",
            reference_id=report_id,
        )
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:
        logger.exception(
            "Reference comparison form failed character_id=%s reference_id=%s job_id=%s",
            page.character.id,
            page.reference.id,
            tracker.job_id,
        )
        await tracker.error(error)


__all__ = ("ReferenceComparisonReplyFilter", "router")
