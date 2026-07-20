from __future__ import annotations

import logging
import os
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from velvet_bot.database import Database
from velvet_bot.domains.public_archive.watermark_repository import (
    PublicArchiveWatermarkRepository,
)
from velvet_bot.domains.watermark.archive_output import (
    prepare_archive_watermark_output,
)
from velvet_bot.domains.watermark.repository import WatermarkRepository
from velvet_bot.domains.watermark.service import WatermarkService
from velvet_bot.domains.watermark.telegram_storage import (
    WatermarkStorageSettings,
    cleanup_watermark_job_files,
    store_archive_watermark,
)
from velvet_bot.infrastructure.krita_bridge import KritaBridge, default_krita_bridge_dir
from velvet_bot.watermark_ui import WatermarkCallback, format_watermark_caption

logger = logging.getLogger(__name__)


def _watermark_enabled() -> bool:
    return os.getenv("KRITA_WATERMARK_ENABLED", "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
        "да",
    }


def _build_service(bot: Bot, database: Database) -> WatermarkService:
    return WatermarkService(
        bot=bot,
        repository=WatermarkRepository(database),
        bridge=KritaBridge(default_krita_bridge_dir()),
    )


async def _safe_finish_card(callback: CallbackQuery, text: str) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        if callback.message.photo or callback.message.document:
            await callback.message.edit_caption(caption=text, reply_markup=None)
        else:
            await callback.message.edit_text(text, reply_markup=None)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


async def handle_archive_watermark_storage_approve(
    callback: CallbackQuery,
    callback_data: WatermarkCallback,
    bot: Bot,
    database: Database,
) -> None:
    if not _watermark_enabled():
        await callback.answer("Krita bridge выключен.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение preview больше недоступно.", show_alert=True)
        return

    await callback.answer("Сохраняю PNG в Telegram-хранилище…")
    service = _build_service(bot, database)
    repository = PublicArchiveWatermarkRepository(database)

    try:
        item = await service.approve(
            callback_data.job_id,
            owner_user_id=callback.from_user.id,
        )
        media_id = item.job.archive_media_id
        if media_id is None:
            raise ValueError("Задание не связано с публичным архивом.")
        if not item.job.final_path:
            raise ValueError("Финальный путь задания не сохранён.")

        output = prepare_archive_watermark_output(
            item.job.source_path,
            item.job.final_path,
        )
        source = await repository.get_source(media_id)
        if source is None:
            raise ValueError("Исходный материал публичного архива больше не найден.")

        storage_settings = WatermarkStorageSettings.from_env()
        stored = await store_archive_watermark(
            bot=bot,
            item=item,
            media_id=media_id,
            output=output,
            source_name=source.file_name,
            character_names=source.character_names,
            settings=storage_settings,
        )
        document = stored.message.document
        if document is None:
            raise ValueError("Telegram-хранилище не вернуло file_id PNG.")

        updated = await repository.approve_replacement(
            media_id=media_id,
            telegram_file_id=document.file_id,
            telegram_file_unique_id=document.file_unique_id,
            file_size=stored.file_size,
            approved_by=callback.from_user.id,
            settings=item.revision.settings,
            storage_chat_id=storage_settings.chat_id,
            storage_thread_id=storage_settings.thread_id,
            storage_message_id=stored.message.message_id,
            storage_sha256=stored.sha256,
        )
        if not updated:
            try:
                await bot.delete_message(
                    chat_id=storage_settings.chat_id,
                    message_id=stored.message.message_id,
                )
            except TelegramAPIError:
                logger.warning(
                    "Could not remove orphan watermark storage message chat=%s message=%s",
                    storage_settings.chat_id,
                    stored.message.message_id,
                )
            raise ValueError("Материал публичного архива больше не найден.")

        deleted_files, freed_bytes = cleanup_watermark_job_files(
            item,
            service.bridge,
        )
        if deleted_files:
            await repository.mark_local_cleaned(media_id)
        logger.info(
            "Stored archive watermark media=%s chat=%s thread=%s message=%s "
            "sha256=%s deleted_files=%s freed_bytes=%s",
            media_id,
            storage_settings.chat_id,
            storage_settings.thread_id,
            stored.message.message_id,
            stored.sha256,
            deleted_files,
            freed_bytes,
        )

        await callback.message.answer(
            "✅ Watermark сохранён в закрытом Telegram-хранилище и заменил "
            "файл публичного архива.\n"
            f"Media ID: <code>{media_id}</code> · "
            f"SHA: <code>{stored.sha256[:12]}</code>\n"
            f'<a href="{stored.message_link}">Открыть файл в хранилище</a>'
        )
        await _safe_finish_card(
            callback,
            format_watermark_caption(
                item,
                status_text="одобрен, сохранён в Telegram и заменён в архиве",
            ),
        )
    except (OSError, TelegramAPIError, TypeError, ValueError) as error:
        logger.warning(
            "Could not store approved archive watermark job=%s: %s",
            callback_data.job_id,
            error,
        )
        await callback.message.answer(f"❌ {escape(str(error))}")


def register_archive_watermark_storage_handler(router: Router) -> None:
    router.callback_query.register(
        handle_archive_watermark_storage_approve,
        WatermarkCallback.filter(F.action == "archive_approve"),
    )


__all__ = ("register_archive_watermark_storage_handler",)
