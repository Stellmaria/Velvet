from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

import velvet_bot.public_archive_display as public_display
from velvet_bot.archive_catalog import ArchivePage
from velvet_bot.archive_preview import (
    persist_preview_from_sent_message,
    resolve_archive_image_preview,
)
from velvet_bot.archive_ui import build_input_media
from velvet_bot.database import Database
from velvet_bot.image_preview import BOT_API_DOWNLOAD_MAX_BYTES, ImagePreviewError
from velvet_bot.public_ui import format_public_archive_caption

_INSTALLED = False


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


async def send_viewer_archive_page(
    *,
    bot: Bot,
    database: Database,
    chat_id: int,
    page: ArchivePage,
    viewer_user_id: int,
    manager_access: bool = False,
    menu_page: int = 0,
    category: str = "",
    universe: str = "",
    story_id: int = 0,
) -> Message:
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")

    state = await public_display.load_public_state(database, page, viewer_user_id)
    keyboard = await public_display.build_viewer_keyboard(
        database,
        page,
        state,
        viewer_user_id=viewer_user_id,
        manager_access=manager_access,
        menu_page=menu_page,
        category=category,
        universe=universe,
        story_id=story_id,
    )
    common = {
        "chat_id": chat_id,
        "caption": format_public_archive_caption(page, state),
        "reply_markup": keyboard,
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

    return await bot.send_document(document=media.telegram_file_id, **common)


async def replace_viewer_archive_page(
    *,
    callback: CallbackQuery,
    bot: Bot,
    database: Database,
    page: ArchivePage,
    viewer_user_id: int,
    manager_access: bool = False,
    menu_page: int = 0,
    category: str = "",
    universe: str = "",
    story_id: int = 0,
) -> None:
    if page.media is None or not isinstance(callback.message, Message):
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return

    state = await public_display.load_public_state(database, page, viewer_user_id)
    keyboard = await public_display.build_viewer_keyboard(
        database,
        page,
        state,
        viewer_user_id=viewer_user_id,
        manager_access=manager_access,
        menu_page=menu_page,
        category=category,
        universe=universe,
        story_id=story_id,
    )

    if page.media.is_image_document:
        photo = await resolve_archive_image_preview(
            bot,
            database,
            page,
            cache_chat_id=callback.message.chat.id,
        )
        if photo is None:
            raise _image_display_error(page)

        from aiogram.enums import ParseMode
        from aiogram.types import InputMediaPhoto

        input_media = InputMediaPhoto(
            media=photo,
            caption=format_public_archive_caption(page, state),
            parse_mode=ParseMode.HTML,
            has_spoiler=page.media.is_spoiler,
        )
    else:
        input_media = build_input_media(
            page.media,
            format_public_archive_caption(page, state),
        )

    try:
        edited = await callback.message.edit_media(
            media=input_media,
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
        await send_viewer_archive_page(
            bot=bot,
            database=database,
            chat_id=callback.message.chat.id,
            page=page,
            viewer_user_id=viewer_user_id,
            manager_access=manager_access,
            menu_page=menu_page,
            category=category,
            universe=universe,
            story_id=story_id,
        )
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass


def install_public_preview_overrides() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    public_display.send_viewer_archive_page = send_viewer_archive_page
    public_display.replace_viewer_archive_page = replace_viewer_archive_page
    _INSTALLED = True
