from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from velvet_bot.archive_catalog import ArchivePage, get_archive_page
from velvet_bot.archive_ui import (
    ArchiveMediaCallback,
    build_archive_navigation,
    build_input_media,
    format_archive_caption,
)
from velvet_bot.database import Database
from velvet_bot.image_preview import build_image_document_preview

router = Router(name=__name__)
logger = logging.getLogger(__name__)


async def build_admin_display_media(bot: Bot, page: ArchivePage):
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")

    caption = format_archive_caption(page)
    if page.media.is_image_document:
        try:
            upload = await build_image_document_preview(bot, page.media)
            return InputMediaPhoto(
                media=upload,
                caption=caption,
                parse_mode=ParseMode.HTML,
                has_spoiler=page.media.is_spoiler,
            )
        except Exception:  # p2-approved-boundary: fallback-admin-edit-preview
            logger.exception("Failed to prepare compressed admin image preview")

    return build_input_media(page.media, caption)


async def send_admin_archive_page(
    *,
    bot: Bot,
    chat_id: int,
    page: ArchivePage,
) -> Message:
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")

    common = {
        "chat_id": chat_id,
        "caption": format_archive_caption(page),
        "reply_markup": build_archive_navigation(page),
    }
    media = page.media

    if media.media_type == "photo":
        return await bot.send_photo(
            photo=media.telegram_file_id,
            has_spoiler=media.is_spoiler,
            **common,
        )
    if media.media_type == "video":
        return await bot.send_video(
            video=media.telegram_file_id,
            has_spoiler=media.is_spoiler,
            **common,
        )
    if media.media_type == "animation":
        return await bot.send_animation(
            animation=media.telegram_file_id,
            has_spoiler=media.is_spoiler,
            **common,
        )
    if media.is_image_document:
        try:
            upload = await build_image_document_preview(bot, media)
            return await bot.send_photo(
                photo=upload,
                has_spoiler=media.is_spoiler,
                **common,
            )
        except TelegramAPIError as error:
            logger.info("Compressed admin preview fallback to document: %s", error)
        except Exception:  # p2-approved-boundary: fallback-admin-send-preview
            logger.exception("Compressed admin preview generation failed")

    return await bot.send_document(document=media.telegram_file_id, **common)


async def replace_admin_archive_page(
    callback: CallbackQuery,
    bot: Bot,
    page: ArchivePage,
) -> None:
    if page.media is None or not isinstance(callback.message, Message):
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return

    media = await build_admin_display_media(bot, page)
    keyboard = build_archive_navigation(page)
    try:
        await callback.message.edit_media(media=media, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" in str(error).casefold():
            await callback.message.edit_reply_markup(reply_markup=keyboard)
            return
        await send_admin_archive_page(
            bot=bot,
            chat_id=callback.message.chat.id,
            page=page,
        )
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass


@router.callback_query(
    ArchiveMediaCallback.filter(F.action.in_({"open", "show", "delno"}))
)
async def handle_admin_archive_display(
    callback: CallbackQuery,
    callback_data: ArchiveMediaCallback,
    database: Database,
    bot: Bot,
) -> None:
    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
    )
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
            await send_admin_archive_page(
                bot=bot,
                chat_id=callback.message.chat.id,
                page=page,
            )
        except TelegramBadRequest as error:
            logger.warning("Failed to send admin archive media: %s", error)
            await callback.answer(
                "Telegram больше не может открыть этот файл.",
                show_alert=True,
            )
            return
        await callback.answer()
        return

    await replace_admin_archive_page(callback, bot, page)
    await callback.answer()
