from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.access import AccessPolicy
from velvet_bot.archive_catalog import get_archive_page
from velvet_bot.character_directory import (
    get_character_directory_item,
    universe_label,
)
from velvet_bot.database import Database
from velvet_bot.presentation.telegram.routers.characters.contracts import (
    AdminDirectoryCallback,
)
from velvet_bot.presentation.telegram.routers.characters.profile_views import (
    build_character_profile_keyboard,
    format_character_profile,
)
from velvet_bot.presentation.telegram.routers.stories.contracts import (
    AdminStoryCallback,
    story_callback,
)
from velvet_bot.multi_story_support import (
    clear_character_stories,
    list_assigned_character_stories,
    toggle_character_story,
)
from velvet_bot.public_archive_display import refresh_viewer_archive_caption
from velvet_bot.public_manager_access import has_public_manager_access
from velvet_bot.public_manager_ui import manager_callback
from velvet_bot.public_ui import PublicArchiveCallback
from velvet_bot.story_catalog import StoryPage, list_story_page

router = Router(name=__name__)


def _selected_label(assignments) -> str:
    if not assignments:
        return "не выбраны"
    return ", ".join(item.story.short_label for item in assignments)


async def _safe_edit_text(
    message: Message,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


async def _safe_edit_caption(
    message: Message,
    caption: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    try:
        await message.edit_caption(
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


_admin_callback = story_callback


def _admin_picker_keyboard(
    *,
    character_id: int,
    category: str,
    directory_page: int,
    story_page: StoryPage,
    selected_ids: set[int],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for story in story_page.items:
        marker = "☑" if story.id in selected_ids else "☐"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker} {story.short_label} · {story.title}",
                    callback_data=_admin_callback(
                        "mtoggle",
                        category=category,
                        directory_page=directory_page,
                        story_page=story_page.page,
                        character_id=character_id,
                        story_id=story.id,
                    ),
                )
            ]
        )
    if story_page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️ Новее",
                    callback_data=_admin_callback(
                        "mpage",
                        category=category,
                        directory_page=directory_page,
                        story_page=(story_page.page - 1) % story_page.total_pages,
                        character_id=character_id,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{story_page.page + 1} / {story_page.total_pages}",
                    callback_data=_admin_callback(
                        "mnoop",
                        category=category,
                        directory_page=directory_page,
                        story_page=story_page.page,
                        character_id=character_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="Старее ▶️",
                    callback_data=_admin_callback(
                        "mpage",
                        category=category,
                        directory_page=directory_page,
                        story_page=(story_page.page + 1) % story_page.total_pages,
                        character_id=character_id,
                    ),
                ),
            ]
        )
    if selected_ids:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Убрать все истории",
                    callback_data=_admin_callback(
                        "mclear",
                        category=category,
                        directory_page=directory_page,
                        story_page=story_page.page,
                        character_id=character_id,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="✅ Готово",
                callback_data=_admin_callback(
                    "mdone",
                    category=category,
                    directory_page=directory_page,
                    story_page=story_page.page,
                    character_id=character_id,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_admin_picker(
    callback: CallbackQuery,
    database: Database,
    *,
    character_id: int,
    category: str,
    directory_page: int,
    story_page_number: int,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    item = await get_character_directory_item(database, character_id)
    if item is None or item.universe != "kr":
        raise SkipHandler
    story_page = await list_story_page(
        database,
        universe="kr",
        page=story_page_number,
    )
    assignments = await list_assigned_character_stories(
        database,
        character_id=character_id,
    )
    selected_ids = {entry.story.id for entry in assignments}
    text = (
        "<b>Истории персонажа КР</b>\n\n"
        f"Персонаж: <b>{escape(item.character.name)}</b>\n"
        f"Выбрано: <b>{escape(_selected_label(assignments))}</b>\n\n"
        "Нажимайте на истории, чтобы включать и снимать их. "
        "Можно выбрать несколько вариантов одновременно.\n"
        f"Страница: <b>{story_page.page + 1}</b> из "
        f"<b>{story_page.total_pages}</b>"
    )
    await _safe_edit_text(
        callback.message,
        text,
        _admin_picker_keyboard(
            character_id=character_id,
            category=category,
            directory_page=directory_page,
            story_page=story_page,
            selected_ids=selected_ids,
        ),
    )


@router.callback_query(AdminDirectoryCallback.filter(F.action == "pickstory"))
async def handle_admin_open_multi_story(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None or item.universe != "kr":
        raise SkipHandler
    await callback.answer()
    await _render_admin_picker(
        callback,
        database,
        character_id=item.character.id,
        category=callback_data.category or item.category or "uncategorized",
        directory_page=callback_data.page,
        story_page_number=0,
    )


@router.callback_query(
    AdminStoryCallback.filter(
        F.action.in_({"mtoggle", "mpage", "mclear", "mdone", "mnoop"})
    )
)
async def handle_admin_multi_story_action(
    callback: CallbackQuery,
    callback_data: AdminStoryCallback,
    database: Database,
) -> None:
    if callback_data.action == "mnoop":
        await callback.answer()
        return
    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None or item.universe != "kr":
        await callback.answer("Персонаж КР больше не найден.", show_alert=True)
        return
    category = callback_data.category or item.category or "uncategorized"
    if callback_data.action == "mtoggle":
        selected = await toggle_character_story(
            database,
            character_id=item.character.id,
            story_id=callback_data.story_id,
            assigned_by=callback.from_user.id,
        )
        await _render_admin_picker(
            callback,
            database,
            character_id=item.character.id,
            category=category,
            directory_page=callback_data.directory_page,
            story_page_number=callback_data.story_page,
        )
        await callback.answer("История добавлена." if selected else "История снята.")
        return
    if callback_data.action == "mclear":
        await clear_character_stories(database, character_id=item.character.id)
        await _render_admin_picker(
            callback,
            database,
            character_id=item.character.id,
            category=category,
            directory_page=callback_data.directory_page,
            story_page_number=callback_data.story_page,
        )
        await callback.answer("Все истории сняты.")
        return
    if callback_data.action == "mpage":
        await _render_admin_picker(
            callback,
            database,
            character_id=item.character.id,
            category=category,
            directory_page=callback_data.directory_page,
            story_page_number=callback_data.story_page,
        )
        await callback.answer()
        return
    if callback_data.action == "mdone":
        if not isinstance(callback.message, Message):
            await callback.answer("Меню больше недоступно.", show_alert=True)
            return
        refreshed = await get_character_directory_item(database, item.character.id)
        if refreshed is None:
            await callback.answer("Персонаж больше не найден.", show_alert=True)
            return
        await _safe_edit_text(
            callback.message,
            format_character_profile(refreshed),
            build_character_profile_keyboard(
                refreshed,
                category=category,
                page=callback_data.directory_page,
            ),
        )
        await callback.answer("Истории сохранены.")


def _public_picker_keyboard(
    *,
    character_id: int,
    offset: int,
    media_id: int,
    story_page: StoryPage,
    selected_ids: set[int],
) -> InlineKeyboardMarkup:
    common = {
        "character_id": character_id,
        "offset": offset,
        "media_id": media_id,
    }
    rows: list[list[InlineKeyboardButton]] = []
    for story in story_page.items:
        marker = "☑" if story.id in selected_ids else "☐"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker} {story.short_label} · {story.title}",
                    callback_data=manager_callback(
                        "pmst",
                        story_id=story.id,
                        page=story_page.page,
                        **common,
                    ),
                )
            ]
        )
    if story_page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️ Новее",
                    callback_data=manager_callback(
                        "pmsp",
                        page=(story_page.page - 1) % story_page.total_pages,
                        **common,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{story_page.page + 1} / {story_page.total_pages}",
                    callback_data=manager_callback("pnoop", **common),
                ),
                InlineKeyboardButton(
                    text="Старее ▶️",
                    callback_data=manager_callback(
                        "pmsp",
                        page=(story_page.page + 1) % story_page.total_pages,
                        **common,
                    ),
                ),
            ]
        )
    if selected_ids:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Убрать все истории",
                    callback_data=manager_callback(
                        "pmsclear",
                        page=story_page.page,
                        **common,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="✅ Готово",
                callback_data=manager_callback("pmsdone", **common),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_public_picker(
    callback: CallbackQuery,
    database: Database,
    *,
    character_id: int,
    offset: int,
    page_number: int,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    archive_page = await get_archive_page(database, character_id, offset)
    item = await get_character_directory_item(database, character_id)
    if (
        archive_page is None
        or archive_page.media is None
        or item is None
        or item.universe != "kr"
    ):
        raise SkipHandler
    story_page = await list_story_page(database, universe="kr", page=page_number)
    assignments = await list_assigned_character_stories(
        database,
        character_id=character_id,
    )
    selected_ids = {entry.story.id for entry in assignments}
    caption = (
        "<b>Истории персонажа КР</b>\n\n"
        f"Персонаж: <b>{escape(item.character.name)}</b>\n"
        f"Вселенная: <b>{escape(universe_label(item.universe))}</b>\n"
        f"Выбрано: <b>{escape(_selected_label(assignments))}</b>\n\n"
        "Можно выбрать несколько историй одновременно.\n"
        f"Страница: <b>{story_page.page + 1}</b> из "
        f"<b>{story_page.total_pages}</b>"
    )
    await _safe_edit_caption(
        callback.message,
        caption,
        _public_picker_keyboard(
            character_id=character_id,
            offset=offset,
            media_id=archive_page.media.id,
            story_page=story_page,
            selected_ids=selected_ids,
        ),
    )


@router.callback_query(
    PublicArchiveCallback.filter(F.action.in_({"psts", "pstp"}))
)
async def handle_public_open_multi_story(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    access_policy: AccessPolicy,
) -> None:
    if not has_public_manager_access(callback.from_user, access_policy):
        raise SkipHandler
    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None or item.universe != "kr":
        raise SkipHandler
    await callback.answer()
    await _render_public_picker(
        callback,
        database,
        character_id=item.character.id,
        offset=callback_data.offset,
        page_number=callback_data.page,
    )


@router.callback_query(
    PublicArchiveCallback.filter(
        F.action.in_({"pmst", "pmsp", "pmsclear", "pmsdone"})
    )
)
async def handle_public_multi_story_action(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    access_policy: AccessPolicy,
) -> None:
    if not has_public_manager_access(callback.from_user, access_policy):
        await callback.answer("Управление архивом для вас закрыто.", show_alert=True)
        return
    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None or item.universe != "kr":
        await callback.answer("Персонаж КР больше не найден.", show_alert=True)
        return
    if callback_data.action == "pmst":
        selected = await toggle_character_story(
            database,
            character_id=item.character.id,
            story_id=callback_data.story_id,
            assigned_by=callback.from_user.id,
        )
        await _render_public_picker(
            callback,
            database,
            character_id=item.character.id,
            offset=callback_data.offset,
            page_number=callback_data.page,
        )
        await callback.answer("История добавлена." if selected else "История снята.")
        return
    if callback_data.action == "pmsclear":
        await clear_character_stories(database, character_id=item.character.id)
        await _render_public_picker(
            callback,
            database,
            character_id=item.character.id,
            offset=callback_data.offset,
            page_number=callback_data.page,
        )
        await callback.answer("Все истории сняты.")
        return
    if callback_data.action == "pmsp":
        await _render_public_picker(
            callback,
            database,
            character_id=item.character.id,
            offset=callback_data.offset,
            page_number=callback_data.page,
        )
        await callback.answer()
        return
    if callback_data.action == "pmsdone":
        archive_page = await get_archive_page(
            database,
            item.character.id,
            callback_data.offset,
        )
        if archive_page is None or archive_page.media is None:
            await callback.answer("Материал больше недоступен.", show_alert=True)
            return
        await refresh_viewer_archive_caption(
            callback=callback,
            database=database,
            page=archive_page,
            viewer_user_id=callback.from_user.id,
            manager_access=True,
        )
        await callback.answer("Истории сохранены.")
