from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import CallbackQuery, Message

from velvet_bot.character_directory import (
    category_label,
    get_character_directory_item,
    universe_label,
)
from velvet_bot.database import Database
from velvet_bot.handlers.admin_directory import (
    AdminDirectoryCallback,
    _profile_keyboard,
)
from velvet_bot.handlers.admin_stories import AdminStoryCallback
from velvet_bot.multi_story_queries import list_assigned_character_stories
from velvet_bot.safe_analytics_edit import safe_analytics_edit

router = Router(name=__name__)


def _kr_profile_text(item, assignments) -> str:
    prompt_line = (
        f'<a href="{escape(item.prompt_post_url, quote=True)}">Пост с промтом</a>'
        if item.prompt_post_url
        else "Промт персонажа: <b>не привязан</b>"
    )
    labels = ", ".join(entry.story.short_label for entry in assignments) or "Без историй"
    public_ready = bool(item.category and item.universe and assignments)
    public_state = (
        "доступен после добавления материалов"
        if public_ready
        else "скрыт, пока не выбрана хотя бы одна история"
    )
    return (
        "<b>Карточка персонажа</b>\n\n"
        f"Имя: <b>{escape(item.character.name)}</b>\n"
        f"Пол / состав: <b>{escape(category_label(item.category))}</b>\n"
        f"Вселенная: <b>{escape(universe_label(item.universe))}</b>\n"
        f"Истории: <b>{escape(labels)}</b>\n"
        f"Материалов: <b>{item.media_count}</b>\n"
        f"Публичный архив: <b>{public_state}</b>\n"
        f"{prompt_line}"
    )


async def _render_kr_profile(
    callback: CallbackQuery,
    database: Database,
    *,
    character_id: int,
    category: str,
    page: int,
) -> bool:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return True
    item = await get_character_directory_item(database, character_id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return True
    if item.universe != "kr":
        return False
    assignments = await list_assigned_character_stories(
        database,
        character_id=character_id,
    )
    await safe_analytics_edit(
        callback,
        _kr_profile_text(item, assignments),
        _profile_keyboard(
            item,
            category=category or item.category or "uncategorized",
            page=page,
        ),
    )
    return True


@router.callback_query(AdminDirectoryCallback.filter(F.action == "profile"))
async def handle_kr_profile(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    handled = await _render_kr_profile(
        callback,
        database,
        character_id=callback_data.character_id,
        category=callback_data.category,
        page=callback_data.page,
    )
    if not handled:
        raise SkipHandler
    await callback.answer()


@router.callback_query(AdminStoryCallback.filter(F.action == "mdone"))
async def handle_kr_multi_story_done(
    callback: CallbackQuery,
    callback_data: AdminStoryCallback,
    database: Database,
) -> None:
    handled = await _render_kr_profile(
        callback,
        database,
        character_id=callback_data.character_id,
        category=callback_data.category,
        page=callback_data.directory_page,
    )
    if not handled:
        raise SkipHandler
    await callback.answer("Истории сохранены.")
