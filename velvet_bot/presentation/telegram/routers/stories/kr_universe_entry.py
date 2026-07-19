from __future__ import annotations

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import CallbackQuery

from velvet_bot.access import AccessPolicy
from velvet_bot.character_directory import (
    get_character_directory_item,
    set_character_universe,
)
from velvet_bot.database import Database
from velvet_bot.presentation.telegram.routers.characters.directory import (
    AdminDirectoryCallback,
)
from velvet_bot.presentation.telegram.routers.stories.multi_story_kr import (
    _render_admin_picker,
    _render_public_picker,
)
from velvet_bot.public_manager_access import has_public_manager_access
from velvet_bot.public_ui import PublicArchiveCallback

router = Router(name=__name__)


@router.callback_query(
    AdminDirectoryCallback.filter((F.action == "setuni") & (F.universe == "kr"))
)
async def handle_admin_set_kr(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    await set_character_universe(
        database,
        character_id=item.character.id,
        universe="kr",
    )
    refreshed = await get_character_directory_item(database, item.character.id)
    if refreshed is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    await _render_admin_picker(
        callback,
        database,
        character_id=refreshed.character.id,
        category=(
            callback_data.return_category
            or refreshed.category
            or "uncategorized"
        ),
        directory_page=callback_data.page,
        story_page_number=0,
    )
    await callback.answer(
        "Вселенная КР назначена. Можно выбрать несколько историй.",
        show_alert=True,
    )


@router.callback_query(
    PublicArchiveCallback.filter((F.action == "puni") & (F.universe == "kr"))
)
async def handle_public_set_kr(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    access_policy: AccessPolicy,
) -> None:
    if not has_public_manager_access(callback.from_user, access_policy):
        raise SkipHandler
    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    await set_character_universe(
        database,
        character_id=item.character.id,
        universe="kr",
    )
    await _render_public_picker(
        callback,
        database,
        character_id=item.character.id,
        offset=callback_data.offset,
        page_number=0,
    )
    await callback.answer(
        "Вселенная КР назначена. Можно выбрать несколько историй.",
        show_alert=True,
    )
