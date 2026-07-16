from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from velvet_bot.archive_catalog import ArchivePage, get_archive_page
from velvet_bot.archive_preview import (
    persist_preview_from_sent_message,
    resolve_archive_image_preview,
)
from velvet_bot.archive_ui import (
    ArchiveMediaCallback,
    build_archive_navigation,
    build_input_media,
    format_archive_caption,
)
from velvet_bot.database import Database
from velvet_bot.image_preview import BOT_API_DOWNLOAD_MAX_BYTES, ImagePreviewError

router = Router(name=__name__)
logger = logging.getLogger(__name__)


def _image_display_error(page: ArchivePage) -> ImagePreviewError:
    media = page.media
    if media is not None and media.file_size is not None:
        if media.file_size > BOT_API_DOWNLOAD_MAX_BYTES:
            return ImagePreviewError(
                "Изображение больше 20 МБ нельзя открыть фотографией через облачный Bot API."
            )
    return ImagePreviewError(
        "Telegram не смог открыть это изображение фотографией в хорошем качестве."
    )


async def _build_display_media(
    bot: Bot,
    database: Database,
    page: ArchivePage,
    *,
    cache_chat_id: int,
):
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")

    caption = format_archive_caption(page)
    if page.media.is_image_document:
        photo = await resolve_archive_image_preview(
            bot,
            database,
            page,
            cache_chat_id=cache_chat_id,
        )
        if photo is None:
            raise _image_display_error(page)
        return InputMediaPhoto(
            media=photo,
            caption=caption,
            parse_mode=ParseMode.HTML,
            has_spoiler=page.media.is_spoiler,
        )
    return build_input_media(page.media, caption)


async def _send_page(
    *,
    bot: Bot,
    database: Database,
    chat_id: int,
    page: ArchivePage,
) -> Message:
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")

    common = {
        "chat_id": chat_id,
        "caption": format_archive_caption(page),
        "reply_markup": build_archive_navigation(page),
        "protect_content": True,
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
        photo = await resolve_archive_image_preview(
            bot,
            database,
            page,
            cache_chat_id=chat_id,
        )
        if photo is None:
            raise _image_display_error(page)
        sent = await bot.send_photo(
            photo=photo,
            has_spoiler=media.is_spoiler,
            **common,
        )
        await persist_preview_from_sent_message(
            database,
            media_id=media.id,
            message=sent,
        )
        return sent

    return await bot.send_document(
        document=media.telegram_file_id,
        **common,
    )


async def _replace_page(
    callback: CallbackQuery,
    bot: Bot,
    database: Database,
    page: ArchivePage,
) -> None:
    if page.media is None or not isinstance(callback.message, Message):
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return

    media = await _build_display_media(
        bot,
        database,
        page,
        cache_chat_id=callback.message.chat.id,
    )
    keyboard = build_archive_navigation(page)
    try:
        edited = await callback.message.edit_media(
            media=media,
            reply_markup=keyboard,
        )
        if page.media.is_image_document:
            await persist_preview_from_sent_message(
                database,
                media_id=page.media.id,
                message=edited,
            )
    except TelegramBadRequest as error:
        if "message is not modified" in str(error).casefold():
            await callback.message.edit_reply_markup(reply_markup=keyboard)
            return
        await _send_page(
            bot=bot,
            database=database,
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
async def handle_admin_large_media_preview(
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

    try:
        if callback_data.action == "open":
            if not isinstance(callback.message, Message):
                await callback.answer("Не удалось определить чат.", show_alert=True)
                return
            await _send_page(
                bot=bot,
                database=database,
                chat_id=callback.message.chat.id,
                page=page,
            )
            await callback.answer()
            return

        await _replace_page(callback, bot, database, page)
        await callback.answer()
    except ImagePreviewError as error:
        await callback.answer(str(error), show_alert=True)
    except TelegramBadRequest as error:
        logger.warning("Failed to send admin archive media: %s", error)
        await callback.answer(
            "Telegram больше не может открыть этот материал.",
            show_alert=True,
        )
