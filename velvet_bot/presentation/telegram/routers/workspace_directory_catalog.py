from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.character_management import load_workspace_character
from velvet_bot.domains.workspaces.directory_catalog import (
    WorkspaceDirectoryPage,
    list_workspace_directory_categories,
    list_workspace_directory_characters,
    list_workspace_directory_stories,
    list_workspace_directory_universes,
)
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.navigation import compact_button_text, two_column_rows


router = Router(name=__name__)


class WorkspaceCatalogCallback(CallbackData, prefix="wcat"):
    action: str
    workspace_id: int
    item_id: int = 0
    page: int = 0
    character_id: int = 0


def _cb(
    action: str,
    *,
    workspace_id: int,
    item_id: int = 0,
    page: int = 0,
    character_id: int = 0,
) -> str:
    return WorkspaceCatalogCallback(
        action=action,
        workspace_id=int(workspace_id),
        item_id=int(item_id),
        page=int(page),
        character_id=int(character_id),
    ).pack()


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _module_enabled(
    database: Database,
    *,
    workspace_id: int,
    module_key: str,
) -> bool:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT is_allowed AND is_enabled
            FROM workspace_modules
            WHERE workspace_id = $1::BIGINT
              AND module_key = $2::VARCHAR
            """,
            int(workspace_id),
            module_key,
        )
    return bool(value)


async def _require_access(
    *,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_id: int,
    user_id: int,
) -> None:
    await workspace_service.require_role(
        workspace_id=int(workspace_id),
        user_id=int(user_id),
        minimum_role="viewer",
        global_owner=_is_global_owner(user_id),
    )
    for module_key in ("characters", "taxonomy"):
        if not await _module_enabled(
            database,
            workspace_id=workspace_id,
            module_key=module_key,
        ):
            raise WorkspaceAccessError(
                "Для каталога должны быть включены модули персонажей и структуры."
            )


async def _taxonomy_id_map(
    database: Database,
    *,
    workspace_id: int,
    table: str,
) -> dict[str, int]:
    if table not in {"workspace_categories", "workspace_universes"}:
        raise ValueError("Неизвестный справочник пространства.")
    async with database.acquire() as connection:
        rows = await connection.fetch(
            f"""
            SELECT id, key
            FROM {table}
            WHERE workspace_id = $1::BIGINT
              AND is_enabled
            """,
            int(workspace_id),
        )
    return {str(row["key"]): int(row["id"]) for row in rows}


async def _resolve_key(
    database: Database,
    *,
    workspace_id: int,
    table: str,
    item_id: int,
) -> str:
    if table not in {"workspace_categories", "workspace_universes"}:
        raise ValueError("Неизвестный справочник пространства.")
    async with database.acquire() as connection:
        value = await connection.fetchval(
            f"""
            SELECT key
            FROM {table}
            WHERE workspace_id = $1::BIGINT
              AND id = $2::BIGINT
              AND is_enabled
            """,
            int(workspace_id),
            int(item_id),
        )
    if value is None:
        raise ValueError("Элемент структуры больше не доступен в этом пространстве.")
    return str(value)


def _root_text(workspace_name: str) -> str:
    return (
        f"<b>🔎 Каталог · {escape(workspace_name)}</b>\n\n"
        "Фильтры строятся из категорий, вселенных и историй этого пространства. "
        "Системные константы Velvet здесь не используются."
    )


def _root_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📁 Категории",
                    callback_data=_cb("categories", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="🎭 Вселенные",
                    callback_data=_cb("universes", workspace_id=workspace_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📖 Истории",
                    callback_data=_cb("storyworlds", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="👥 Все персонажи",
                    callback_data=_cb("all", workspace_id=workspace_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✖ Закрыть",
                    callback_data=_cb("close", workspace_id=workspace_id),
                )
            ],
        ]
    )


async def _categories_keyboard(
    database: Database,
    *,
    workspace_id: int,
) -> InlineKeyboardMarkup:
    summaries = await list_workspace_directory_categories(
        database,
        workspace_id=workspace_id,
        include_uncategorized=True,
    )
    ids = await _taxonomy_id_map(
        database,
        workspace_id=workspace_id,
        table="workspace_categories",
    )
    buttons = [
        InlineKeyboardButton(
            text=compact_button_text(
                f"{item.emoji} {item.label} · {item.character_count}"
            ),
            callback_data=_cb(
                "cchars",
                workspace_id=workspace_id,
                item_id=(-1 if item.key == "uncategorized" else ids[item.key]),
            ),
        )
        for item in summaries
    ]
    rows = two_column_rows(buttons)
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Каталог",
                callback_data=_cb("root", workspace_id=workspace_id),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _universes_keyboard(
    database: Database,
    *,
    workspace_id: int,
    action: str,
) -> InlineKeyboardMarkup:
    summaries = await list_workspace_directory_universes(
        database,
        workspace_id=workspace_id,
        include_unassigned=(action == "uchars"),
    )
    ids = await _taxonomy_id_map(
        database,
        workspace_id=workspace_id,
        table="workspace_universes",
    )
    buttons = [
        InlineKeyboardButton(
            text=compact_button_text(
                f"{item.emoji} {item.label} · {item.character_count}"
            ),
            callback_data=_cb(
                action,
                workspace_id=workspace_id,
                item_id=(-1 if item.key == "unassigned" else ids[item.key]),
            ),
        )
        for item in summaries
    ]
    rows = two_column_rows(buttons)
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Каталог",
                callback_data=_cb("root", workspace_id=workspace_id),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _stories_keyboard(
    database: Database,
    *,
    workspace_id: int,
    universe_id: int,
) -> InlineKeyboardMarkup:
    universe_key = await _resolve_key(
        database,
        workspace_id=workspace_id,
        table="workspace_universes",
        item_id=universe_id,
    )
    stories = await list_workspace_directory_stories(
        database,
        workspace_id=workspace_id,
        universe_key=universe_key,
    )
    rows = [
        [
            InlineKeyboardButton(
                text=compact_button_text(
                    f"📖 {item.short_label} · {item.title} · {item.character_count}"
                ),
                callback_data=_cb(
                    "schars",
                    workspace_id=workspace_id,
                    item_id=item.id,
                ),
            )
        ]
        for item in stories
    ]
    if not rows:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Историй пока нет",
                    callback_data=_cb("noop", workspace_id=workspace_id),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Вселенные",
                callback_data=_cb("storyworlds", workspace_id=workspace_id),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _page_text(page: WorkspaceDirectoryPage, title: str) -> str:
    return (
        f"<b>{escape(title)}</b>\n\n"
        f"Персонажей: <b>{page.total_items}</b>\n"
        f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>"
    )


def _page_keyboard(
    page: WorkspaceDirectoryPage,
    *,
    workspace_id: int,
    source_action: str,
    source_id: int,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=compact_button_text(
                    "👤 "
                    + item.name
                    + " · "
                    + (item.universe_label or "без вселенной")
                    + " · "
                    + (item.primary_story_short_label or "—")
                    + f" · {item.media_count}"
                ),
                callback_data=_cb(
                    "profile",
                    workspace_id=workspace_id,
                    item_id=source_id,
                    page=page.page,
                    character_id=item.id,
                ),
            )
        ]
        for item in page.items
    ]
    if page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_cb(
                        source_action,
                        workspace_id=workspace_id,
                        item_id=source_id,
                        page=(page.page - 1) % page.total_pages,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1}/{page.total_pages}",
                    callback_data=_cb("noop", workspace_id=workspace_id),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_cb(
                        source_action,
                        workspace_id=workspace_id,
                        item_id=source_id,
                        page=(page.page + 1) % page.total_pages,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Каталог",
                callback_data=_cb("root", workspace_id=workspace_id),
            ),
            InlineKeyboardButton(
                text="✖ Закрыть",
                callback_data=_cb("close", workspace_id=workspace_id),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_page(
    database: Database,
    *,
    workspace_id: int,
    action: str,
    item_id: int,
    page_number: int,
) -> tuple[str, InlineKeyboardMarkup]:
    category_key = None
    universe_key = None
    story_id = None
    title = "👥 Все персонажи"
    if action == "cchars":
        category_key = (
            "uncategorized"
            if item_id == -1
            else await _resolve_key(
                database,
                workspace_id=workspace_id,
                table="workspace_categories",
                item_id=item_id,
            )
        )
        title = "📁 Категория · " + category_key
    elif action == "uchars":
        universe_key = (
            "unassigned"
            if item_id == -1
            else await _resolve_key(
                database,
                workspace_id=workspace_id,
                table="workspace_universes",
                item_id=item_id,
            )
        )
        title = "🎭 Вселенная · " + universe_key
    elif action == "schars":
        story_id = item_id
        async with database.acquire() as connection:
            story = await connection.fetchrow(
                """
                SELECT short_label, title
                FROM workspace_stories
                WHERE workspace_id = $1::BIGINT
                  AND id = $2::BIGINT
                  AND is_enabled
                """,
                int(workspace_id),
                int(story_id),
            )
        if story is None:
            raise ValueError("История больше не доступна в этом пространстве.")
        title = f"📖 {story['short_label']} · {story['title']}"

    page = await list_workspace_directory_characters(
        database,
        workspace_id=workspace_id,
        category_key=category_key,
        universe_key=universe_key,
        story_id=story_id,
        page=page_number,
    )
    return (
        _page_text(page, title),
        _page_keyboard(
            page,
            workspace_id=workspace_id,
            source_action=action,
            source_id=item_id,
        ),
    )


async def _edit(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                raise
    await callback.answer()


@router.message(Command("wcatalog", "workspace_catalog"))
async def handle_workspace_catalog_command(
    message: Message,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    try:
        workspace = await workspace_service.resolve_active_workspace(
            user_id=user_id,
            global_owner=_is_global_owner(user_id),
        )
        if workspace.id == DEFAULT_WORKSPACE_ID:
            await message.answer(
                "Системный Velvet использует существующий каталог <code>/characters</code>."
            )
            return
        await _require_access(
            database=database,
            workspace_service=workspace_service,
            workspace_id=workspace.id,
            user_id=user_id,
        )
    except WorkspaceAccessError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(
        _root_text(workspace.name),
        reply_markup=_root_keyboard(workspace.id),
    )


@router.callback_query(WorkspaceCatalogCallback.filter())
async def handle_workspace_catalog_callback(
    callback: CallbackQuery,
    callback_data: WorkspaceCatalogCallback,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    if callback_data.action == "noop":
        await callback.answer()
        return
    if callback_data.action == "close":
        if isinstance(callback.message, Message):
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
        await callback.answer()
        return

    user_id = callback.from_user.id
    try:
        workspace = await workspace_service.set_active_workspace(
            workspace_id=int(callback_data.workspace_id),
            user_id=user_id,
            global_owner=_is_global_owner(user_id),
        )
        if workspace.id == DEFAULT_WORKSPACE_ID:
            raise WorkspaceAccessError(
                "Системный Velvet использует существующий каталог персонажей."
            )
        await _require_access(
            database=database,
            workspace_service=workspace_service,
            workspace_id=workspace.id,
            user_id=user_id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return

    try:
        action = callback_data.action
        if action == "root":
            await _edit(
                callback,
                text=_root_text(workspace.name),
                reply_markup=_root_keyboard(workspace.id),
            )
            return
        if action == "categories":
            await _edit(
                callback,
                text=f"<b>📁 Категории · {escape(workspace.name)}</b>",
                reply_markup=await _categories_keyboard(
                    database,
                    workspace_id=workspace.id,
                ),
            )
            return
        if action == "universes":
            await _edit(
                callback,
                text=f"<b>🎭 Вселенные · {escape(workspace.name)}</b>",
                reply_markup=await _universes_keyboard(
                    database,
                    workspace_id=workspace.id,
                    action="uchars",
                ),
            )
            return
        if action == "storyworlds":
            await _edit(
                callback,
                text=f"<b>📖 Выберите вселенную · {escape(workspace.name)}</b>",
                reply_markup=await _universes_keyboard(
                    database,
                    workspace_id=workspace.id,
                    action="stories",
                ),
            )
            return
        if action == "stories":
            await _edit(
                callback,
                text=f"<b>📖 Истории · {escape(workspace.name)}</b>",
                reply_markup=await _stories_keyboard(
                    database,
                    workspace_id=workspace.id,
                    universe_id=callback_data.item_id,
                ),
            )
            return
        if action in {"all", "cchars", "uchars", "schars"}:
            text, keyboard = await _render_page(
                database,
                workspace_id=workspace.id,
                action=action,
                item_id=callback_data.item_id,
                page_number=callback_data.page,
            )
            await _edit(callback, text=text, reply_markup=keyboard)
            return
        if action == "profile":
            item = await load_workspace_character(
                database,
                workspace_id=workspace.id,
                character_id=callback_data.character_id,
            )
            if item is None:
                await callback.answer("Персонаж больше не найден.", show_alert=True)
                return
            stories = "\n".join(
                f"{'⭐' if story.is_primary else '📖'} "
                f"{escape(story.short_label)} · {escape(story.title)}"
                for story in item.stories
            ) or "Не назначены."
            text = (
                "<b>Карточка персонажа</b>\n\n"
                f"Имя: <b>{escape(item.name)}</b>\n"
                f"Категория: <b>{escape(item.category or 'не выбрана')}</b>\n"
                f"Вселенная: <b>{escape(item.universe or 'не выбрана')}</b>\n"
                f"Материалов: <b>{item.media_count}</b>\n\n"
                f"<b>Истории</b>\n{stories}"
            )
            await _edit(
                callback,
                text=text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="↩️ К списку",
                                callback_data=_cb(
                                    "all",
                                    workspace_id=workspace.id,
                                    page=callback_data.page,
                                ),
                            )
                        ]
                    ]
                ),
            )
            return
        await callback.answer("Неизвестное действие.", show_alert=True)
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)


__all__ = ("router",)
