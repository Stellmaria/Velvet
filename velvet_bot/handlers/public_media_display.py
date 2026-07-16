from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from velvet_bot.access import AccessPolicy
from velvet_bot.archive_catalog import get_archive_page
from velvet_bot.database import Database
from velvet_bot.public_archive_display import refresh_viewer_archive_caption
from velvet_bot.public_catalog import (
    toggle_character_subscription,
    toggle_public_like,
)
from velvet_bot.public_manager_access import has_public_manager_access
from velvet_bot.public_media_lookup import get_character_media_offset
from velvet_bot.public_preview_overrides import (
    replace_viewer_archive_page,
    send_viewer_archive_page,
)
from velvet_bot.public_ui import PublicArchiveCallback

router = Router(name=__name__)


@router.callback_query(
    PublicArchiveCallback.filter(F.action.in_({"open", "show"}))
)
async def handle_spoiler_aware_open(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
    access_policy: AccessPolicy,
) -> None:
    offset = callback_data.offset
    if callback_data.action == "open" and callback_data.media_id:
        exact_offset = await get_character_media_offset(
            database,
            character_id=callback_data.character_id,
            media_id=callback_data.media_id,
        )
        if exact_offset is None:
            await callback.answer("Материал уже удалён.", show_alert=True)
            return
        offset = exact_offset

    page = await get_archive_page(database, callback_data.character_id, offset)
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return

    manager_access = has_public_manager_access(callback.from_user, access_policy)
    if callback_data.action == "open":
        if not isinstance(callback.message, Message):
            await callback.answer("Не удалось определить чат.", show_alert=True)
            return
        await send_viewer_archive_page(
            bot=bot,
            database=database,
            chat_id=callback.message.chat.id,
            page=page,
            viewer_user_id=callback.from_user.id,
            manager_access=manager_access,
            menu_page=callback_data.page,
            category=callback_data.category,
            universe=callback_data.universe,
            story_id=callback_data.story_id,
        )
    else:
        await replace_viewer_archive_page(
            callback=callback,
            bot=bot,
            database=database,
            page=page,
            viewer_user_id=callback.from_user.id,
            manager_access=manager_access,
            menu_page=callback_data.page,
            category=callback_data.category,
            universe=callback_data.universe,
            story_id=callback_data.story_id,
        )
    await callback.answer()


@router.callback_query(
    PublicArchiveCallback.filter(F.action.in_({"like", "sub"}))
)
async def handle_like_and_subscription(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    access_policy: AccessPolicy,
) -> None:
    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return

    if callback_data.action == "like":
        liked, _ = await toggle_public_like(
            database,
            character_id=page.character.id,
            media_id=page.media.id,
            user_id=callback.from_user.id,
        )
        alert = "Отметка поставлена." if liked else "Отметка снята."
    else:
        subscribed = await toggle_character_subscription(
            database,
            character_id=page.character.id,
            user_id=callback.from_user.id,
        )
        alert = "Подписка включена." if subscribed else "Подписка отключена."

    await refresh_viewer_archive_caption(
        callback=callback,
        database=database,
        page=page,
        viewer_user_id=callback.from_user.id,
        manager_access=has_public_manager_access(callback.from_user, access_policy),
        menu_page=callback_data.page,
        category=callback_data.category,
        universe=callback_data.universe,
        story_id=callback_data.story_id,
    )
    await callback.answer(alert)
