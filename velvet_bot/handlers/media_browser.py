from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from velvet_bot.archive_catalog import ArchivePage, get_archive_page
from velvet_bot.archive_ui import (
    ArchiveMediaCallback,
    build_archive_navigation,
    build_input_media,
    format_archive_caption,
)
from velvet_bot.database import Database

router = Router(name=__name__)
logger = logging.getLogger(__name__)


async def _send_archive_page(
    bot: Bot,
    chat_id: int,
    page: ArchivePage,
) -> Message:
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")

    caption = format_archive_caption(page)
    keyboard = build_archive_navigation(page)
    common = {
        "chat_id": chat_id,
        "caption": caption,
        "reply_markup": keyboard,
    }

    if page.media.media_type == "photo":
        return await bot.send_photo(photo=page.media.telegram_file_id, **common)
    if page.media.media_type == "video":
        return await bot.send_video(video=page.media.telegram_file_id, **common)
    if page.media.media_type == "animation":
        return await bot.send_animation(animation=page.media.telegram_file_id, **common)
    return await bot.send_document(document=page.media.telegram_file_id, **common)


async def _replace_archive_page(
    callback: CallbackQuery,
    bot: Bot,
    page: ArchivePage,
) -> None:
    if page.media is None:
        await callback.answer("Архив персонажа пуст.", show_alert=True)
        return

    callback_message = callback.message
    if not isinstance(callback_message, Message):
        await callback.answer("Сообщение архива больше недоступно.", show_alert=True)
        return

    input_media = build_input_media(page.media, format_archive_caption(page))
    keyboard = build_archive_navigation(page)

    try:
        await callback_message.edit_media(
            media=input_media,
            reply_markup=keyboard,
        )
    except TelegramBadRequest as edit_error:
        logger.info("Archive media edit fallback: %s", edit_error)
        try:
            await _send_archive_page(bot, callback_message.chat.id, page)
        except TelegramBadRequest as send_error:
            logger.warning("Archived Telegram file is unavailable: %s", send_error)
            await callback.answer(
                "Telegram больше не может открыть этот файл.",
                show_alert=True,
            )
            return

        try:
            await callback_message.delete()
        except TelegramBadRequest:
            pass

    await callback.answer()


@router.callback_query(ArchiveMediaCallback.filter())
async def handle_archive_media_callback(
    callback: CallbackQuery,
    callback_data: ArchiveMediaCallback,
    database: Database,
    bot: Bot,
) -> None:
    if callback_data.action == "noop":
        await callback.answer()
        return

    if callback_data.action == "close":
        if isinstance(callback.message, Message):
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
        await callback.answer()
        return

    try:
        page = await get_archive_page(
            database,
            callback_data.character_id,
            callback_data.offset,
        )
    except Exception:
        logger.exception("Failed to load character archive page")
        await callback.answer(
            "Не удалось загрузить архив из базы.",
            show_alert=True,
        )
        return

    if page is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    if page.media is None:
        await callback.answer("Архив персонажа пока пуст.", show_alert=True)
        return

    if callback_data.action == "open":
        if not isinstance(callback.message, Message):
            await callback.answer("Не удалось определить чат.", show_alert=True)
            return
        try:
            await _send_archive_page(bot, callback.message.chat.id, page)
        except TelegramBadRequest as error:
            logger.warning("Failed to send archived media: %s", error)
            await callback.answer(
                "Telegram больше не может открыть этот файл.",
                show_alert=True,
            )
            return
        await callback.answer()
        return

    if callback_data.action == "show":
        await _replace_archive_page(callback, bot, page)
        return

    await callback.answer("Неизвестное действие.", show_alert=True)
