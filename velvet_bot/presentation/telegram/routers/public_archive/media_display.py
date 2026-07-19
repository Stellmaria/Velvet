from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from velvet_bot.access import AccessPolicy
from velvet_bot.archive_catalog import (
    get_archive_page,
    toggle_archive_media_adult_requirement,
    toggle_archive_media_public_visibility,
)
from velvet_bot.database import Database
from velvet_bot.image_preview import ImagePreviewError
from velvet_bot.public_adult_access import has_adult_channel_access
from velvet_bot.public_archive_display import (
    refresh_viewer_archive_caption,
    replace_viewer_archive_page,
)
from velvet_bot.public_catalog import (
    toggle_character_subscription,
    toggle_public_like,
)
from velvet_bot.public_manager_access import has_public_manager_access
from velvet_bot.public_manager_preview_bridge import connect_public_manager_preview
from velvet_bot.public_media_lookup import get_character_media_offset
from velvet_bot.public_preview_overrides import (
    replace_viewer_archive_page as replace_preview_archive_page,
    send_viewer_archive_page,
)
from velvet_bot.public_ui import PublicArchiveCallback

connect_public_manager_preview()
router = Router(name=__name__)


async def _check_media_access(
    callback: CallbackQuery,
    bot: Bot,
    *,
    requires_adult_channel: bool,
    manager_access: bool,
) -> bool:
    if manager_access or not requires_adult_channel:
        return True
    if await has_adult_channel_access(bot, callback.from_user.id):
        return True
    await callback.answer(
        "Этот материал доступен только подписчикам канала Velvet +18.",
        show_alert=True,
    )
    return False


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
    manager_access = has_public_manager_access(callback.from_user, access_policy)
    public_only = not manager_access
    offset = callback_data.offset
    if callback_data.action == "open" and callback_data.media_id:
        exact_offset = await get_character_media_offset(
            database,
            character_id=callback_data.character_id,
            media_id=callback_data.media_id,
            public_only=public_only,
        )
        if exact_offset is None:
            await callback.answer("Материал уже удалён или скрыт.", show_alert=True)
            return
        offset = exact_offset

    page = await get_archive_page(
        database,
        callback_data.character_id,
        offset,
        public_only=public_only,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return
    if not await _check_media_access(
        callback,
        bot,
        requires_adult_channel=page.media.requires_adult_channel,
        manager_access=manager_access,
    ):
        return

    try:
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
            await replace_preview_archive_page(
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
    except ImagePreviewError as error:
        await callback.answer(str(error), show_alert=True)
        return

    await callback.answer()


@router.callback_query(
    PublicArchiveCallback.filter(F.action.in_({"like", "sub"}))
)
async def handle_like_and_subscription(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
    access_policy: AccessPolicy,
) -> None:
    manager_access = has_public_manager_access(callback.from_user, access_policy)
    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
        public_only=not manager_access,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return
    if not await _check_media_access(
        callback,
        bot,
        requires_adult_channel=page.media.requires_adult_channel,
        manager_access=manager_access,
    ):
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
        manager_access=manager_access,
        menu_page=callback_data.page,
        category=callback_data.category,
        universe=callback_data.universe,
        story_id=callback_data.story_id,
    )
    await callback.answer(alert)


@router.callback_query(
    PublicArchiveCallback.filter(F.action.in_({"ppub", "p18"}))
)
async def handle_manager_access_flags(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
    access_policy: AccessPolicy,
) -> None:
    if not has_public_manager_access(callback.from_user, access_policy):
        await callback.answer("Управление архивом для вас закрыто.", show_alert=True)
        return

    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return

    if callback_data.action == "ppub":
        enabled = await toggle_archive_media_public_visibility(
            database,
            character_id=page.character.id,
            media_id=page.media.id,
        )
        alert = (
            "Материал возвращён в публичный архив."
            if enabled
            else "Материал скрыт из публичного архива."
        )
    else:
        enabled = await toggle_archive_media_adult_requirement(
            database,
            character_id=page.character.id,
            media_id=page.media.id,
        )
        alert = (
            "Для материала включена проверка подписки на канал +18."
            if enabled
            else "Проверка подписки на канал +18 отключена."
        )

    updated_page = await get_archive_page(
        database,
        page.character.id,
        page.offset,
    )
    if updated_page is None or updated_page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return
    await replace_viewer_archive_page(
        callback=callback,
        bot=bot,
        database=database,
        page=updated_page,
        viewer_user_id=callback.from_user.id,
        manager_access=True,
    )
    await callback.answer(alert, show_alert=True)
