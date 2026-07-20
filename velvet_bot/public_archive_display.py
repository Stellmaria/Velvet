from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from velvet_bot.archive_catalog import ArchivePage
from velvet_bot.archive_ui import build_input_media
from velvet_bot.character_directory import get_character_directory_item
from velvet_bot.database import Database
from velvet_bot.image_preview import build_image_document_preview
from velvet_bot.public_catalog import get_public_media_state
from velvet_bot.public_manager_ui import build_manager_archive_keyboard
from velvet_bot.public_ui import build_public_archive_keyboard, format_public_archive_caption

logger = logging.getLogger(__name__)


async def load_public_state(
    database: Database,
    page: ArchivePage,
    user_id: int,
):
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


def build_viewer_caption(page: ArchivePage, state, *, manager_access: bool = False) -> str:
    caption = format_public_archive_caption(page, state)
    if not manager_access or page.media is None:
        return caption
    visibility = "показывается" if page.media.is_public else "скрыт"
    adult = "требуется подписка" if page.media.requires_adult_channel else "обычный доступ"
    if state.watermark_approved:
        watermark = "одобрен для публичного скачивания"
    elif state.watermark_applied:
        watermark = "нанесён, ожидает одобрения"
    else:
        watermark = "нет"
    owner_review = "✅ просмотрено" if state.reviewed_by_owner else "🆕 не просмотрено"
    return (
        f"{caption}\n"
        f"Подписок на героя: <b>{state.subscriber_count}</b>\n"
        f"Просмотров: <b>{state.view_count}</b>\n"
        f"Скачиваний: <b>{state.download_count}</b>\n"
        f"Просмотрено Стэл: <b>{owner_review}</b>\n"
        f"Watermark: <b>{watermark}</b>\n"
        f"Публичный архив: <b>{visibility}</b>\n"
        f"Канал +18: <b>{adult}</b>"
    )


async def build_viewer_keyboard(
    database: Database,
    page: ArchivePage,
    state,
    *,
    viewer_user_id: int,
    manager_access: bool = False,
    can_download: bool = False,
    menu_page: int = 0,
    category: str = "",
    universe: str = "",
    story_id: int = 0,
):
    if manager_access:
        category, universe, story_id = await actual_character_filters(
            database,
            page.character.id,
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
        can_download=can_download,
        menu_page=menu_page,
        category=category,
        universe=universe,
        story_id=story_id,
    )


async def build_viewer_input_media(
    bot: Bot,
    page: ArchivePage,
    state,
    *,
    manager_access: bool = False,
):
    if page.media is None:
        raise ValueError("Архив персонажа пуст.")
    caption = build_viewer_caption(page, state, manager_access=manager_access)
    if page.media.is_image_document:
        try:
            upload = await build_image_document_preview(bot, page.media)
            return InputMediaPhoto(
                media=upload,
                caption=caption,
                parse_mode=ParseMode.HTML,
                has_spoiler=page.media.is_spoiler,
            )
        except Exception:  # p2-approved-boundary: fallback-viewer-edit-preview
            logger.exception("Failed to prepare compressed public image preview")
    return build_input_media(page.media, caption)


async def send_viewer_archive_page(
    *,
    bot: Bot,
    database: Database,
    chat_id: int,
    page: ArchivePage,
    viewer_user_id: int,
    manager_access: bool = False,
    can_download: bool = False,
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
        can_download=can_download,
        menu_page=menu_page,
        category=category,
        universe=universe,
        story_id=story_id,
    )
    common = {
        "chat_id": chat_id,
        "caption": build_viewer_caption(page, state, manager_access=manager_access),
        "reply_markup": keyboard,
    }
    if page.media.media_type == "photo":
        return await bot.send_photo(
            photo=page.media.telegram_file_id,
            has_spoiler=page.media.is_spoiler,
            **common,
        )
    if page.media.media_type == "video":
        return await bot.send_video(
            video=page.media.telegram_file_id,
            has_spoiler=page.media.is_spoiler,
            **common,
        )
    if page.media.media_type == "animation":
        return await bot.send_animation(
            animation=page.media.telegram_file_id,
            has_spoiler=page.media.is_spoiler,
            **common,
        )
    if page.media.is_image_document:
        try:
            upload = await build_image_document_preview(bot, page.media)
            return await bot.send_photo(
                photo=upload,
                has_spoiler=page.media.is_spoiler,
                **common,
            )
        except TelegramAPIError as error:
            logger.info("Compressed public preview fallback to document: %s", error)
        except Exception:  # p2-approved-boundary: fallback-viewer-send-preview
            logger.exception("Compressed public preview generation failed")
    return await bot.send_document(document=page.media.telegram_file_id, **common)


async def replace_viewer_archive_page(
    *,
    callback: CallbackQuery,
    bot: Bot,
    database: Database,
    page: ArchivePage,
    viewer_user_id: int,
    manager_access: bool = False,
    can_download: bool = False,
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
        page,
        state,
        manager_access=manager_access,
    )
    keyboard = await build_viewer_keyboard(
        database,
        page,
        state,
        viewer_user_id=viewer_user_id,
        manager_access=manager_access,
        can_download=can_download,
        menu_page=menu_page,
        category=category,
        universe=universe,
        story_id=story_id,
    )
    try:
        await callback.message.edit_media(media=media, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" in str(error).casefold():
            return
        await send_viewer_archive_page(
            bot=bot,
            database=database,
            chat_id=callback.message.chat.id,
            page=page,
            viewer_user_id=viewer_user_id,
            manager_access=manager_access,
            can_download=can_download,
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
    can_download: bool = False,
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
        can_download=can_download,
        menu_page=menu_page,
        category=category,
        universe=universe,
        story_id=story_id,
    )
    await callback.message.edit_caption(
        caption=build_viewer_caption(page, state, manager_access=manager_access),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )
