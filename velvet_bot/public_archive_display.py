from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from velvet_bot.archive_catalog import ArchivePage
from velvet_bot.archive_preview import (
    persist_preview_from_sent_message,
    resolve_archive_image_preview,
)
from velvet_bot.archive_ui import build_input_media
from velvet_bot.character_directory import get_character_directory_item
from velvet_bot.database import Database
from velvet_bot.public_catalog import get_public_media_state
from velvet_bot.public_manager_ui import build_manager_archive_keyboard
from velvet_bot.public_ui import build_public_archive_keyboard, format_public_archive_caption

logger = logging.getLogger(__name__)


async def load_public_state(database: Database, page: ArchivePage, user_id: int):
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")
    return await get_public_media_state(
        database,
        character_id=page.character.id,
        media_id=page.media.id,
        user_id=user_id,
    )


async def actual_character_filters(
    database: Database,
    character_id: int,
) -> tuple[str, str, int]:
    item = await get_character_directory_item(database, character_id)
    if item is None:
        return "", "", 0
    return item.category or "", item.universe or "", item.story_id or 0


async def build_viewer_keyboard(
    database: Database,
    page: ArchivePage,
    state,
    *,
    viewer_user_id: int,
    manager_access: bool = False,
    menu_page: int = 0,
    category: str = "",
    universe: str = "",
    story_id: int = 0,
):
    if manager_access:
        category, universe, story_id = await actual_character_filters(
            database, page.character.id
        )
        return build_manager_archive_keyboard(
            page,
            state,
            category=category,
            universe=universe,
            story_id=story_id,
        )
    return build_public_archive_keyboard(
        page,
        state,
        viewer_user_id=viewer_user_id,
        menu_page=menu_page,
        category=category,
        universe=universe,
        story_id=story_id,
    )


async def build_viewer_input_media(
    bot: Bot,
    database: Database,
    page: ArchivePage,
    state,
    *,
    cache_chat_id: int,
):
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")
    caption = format_public_archive_caption(page, state)
    if page.media.is_image_document:
        preview = await resolve_archive_image_preview(
            bot,
            database,
            page,
            cache_chat_id=cache_chat_id,
        )
        if preview is not None:
            return InputMediaPhoto(
                media=preview,
                caption=caption,
                parse_mode=ParseMode.HTML,
                has_spoiler=page.media.is_spoiler,
            )
    return build_input_media(page.media, caption)


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
    state = await load_public_state(database, page, viewer_user_id)
    keyboard = await build_viewer_keyboard(
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
        preview = await resolve_archive_image_preview(
            bot,
            database,
            page,
            cache_chat_id=chat_id,
        )
        if preview is not None:
            sent = await bot.send_photo(
                photo=preview,
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
    state = await load_public_state(database, page, viewer_user_id)
    media = await build_viewer_input_media(
        bot,
        database,
        page,
        state,
        cache_chat_id=callback.message.chat.id,
    )
    keyboard = await build_viewer_keyboard(
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
    try:
        edited = await callback.message.edit_media(media=media, reply_markup=keyboard)
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


async def refresh_viewer_archive_caption(
    *,
    callback: CallbackQuery,
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
    state = await load_public_state(database, page, viewer_user_id)
    keyboard = await build_viewer_keyboard(
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
    await callback.message.edit_caption(
        caption=format_public_archive_caption(page, state),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )
