from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from velvet_bot.character_directory import (
    get_character_directory_item,
    set_character_universe,
    universe_label,
)
from velvet_bot.database import Database
from velvet_bot.presentation.telegram.routers.characters.directory import (
    AdminDirectoryCallback,
)
from velvet_bot.presentation.telegram.routers.stories.management import (
    build_story_picker,
)
from velvet_bot.story_catalog import list_story_page, universe_requires_story

router = Router(name=__name__)


@router.callback_query(
    AdminDirectoryCallback.filter(
        (F.action == "setuni")
        & F.universe.in_({"shs", "kr", "lm", "idm", "lagerta"})
    )
)
async def handle_universe_with_story_assignment(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    if not universe_requires_story(callback_data.universe):
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return

    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return

    await set_character_universe(
        database,
        character_id=item.character.id,
        universe=callback_data.universe,
    )
    item = await get_character_directory_item(database, item.character.id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return

    story_page = await list_story_page(
        database,
        universe=callback_data.universe,
        page=0,
    )
    if not story_page.items:
        await callback.answer(
            "Для этой вселенной пока нет историй.",
            show_alert=True,
        )
        return

    return_category = (
        callback_data.return_category
        or item.category
        or "uncategorized"
    )
    await callback.message.edit_text(
        "<b>Назначить историю</b>\n\n"
        f"Персонаж: <b>{escape(item.character.name)}</b>\n"
        f"Вселенная: <b>{escape(universe_label(item.universe))}</b>\n\n"
        "Выберите историю. Список идёт от новых к старым.",
        reply_markup=build_story_picker(
            item,
            story_page,
            category=return_category,
            directory_page=callback_data.page,
        ),
    )
    await callback.answer(
        f"{item.character.name}: {universe_label(item.universe)}. "
        "Теперь выберите историю.",
        show_alert=True,
    )
