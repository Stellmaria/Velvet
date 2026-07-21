from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.character_management import (
    WorkspaceCharacterRecord,
    load_workspace_character,
    set_workspace_character_category,
    set_workspace_character_universe,
    toggle_workspace_character_story,
)
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.navigation import compact_button_text, two_column_rows

router = Router(name=__name__)


class WorkspaceCharacterEditCallback(CallbackData, prefix="wced"):
    action: str
    workspace_id: int
    character_id: int
    item_id: int = 0


def _cb(
    action: str,
    *,
    workspace_id: int,
    character_id: int,
    item_id: int = 0,
) -> str:
    return WorkspaceCharacterEditCallback(
        action=action,
        workspace_id=int(workspace_id),
        character_id=int(character_id),
        item_id=int(item_id),
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


async def _require_editor(
    *,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_id: int,
    user_id: int,
) -> None:
    await workspace_service.require_role(
        workspace_id=int(workspace_id),
        user_id=int(user_id),
        minimum_role="editor",
        global_owner=_is_global_owner(user_id),
    )
    for module_key in ("characters", "taxonomy"):
        if not await _module_enabled(
            database,
            workspace_id=workspace_id,
            module_key=module_key,
        ):
            raise WorkspaceAccessError(
                "Для редактора должны быть включены модули персонажей и структуры."
            )


async def _taxonomy_value(
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
        raise ValueError("Значение структуры не найдено в этом пространстве.")
    return str(value)


def _story_lines(item: WorkspaceCharacterRecord) -> str:
    if not item.stories:
        return "Не назначены."
    return "\n".join(
        f"{'⭐' if story.is_primary else '📖'} "
        f"{escape(story.short_label)} · {escape(story.title)}"
        for story in item.stories
    )


def _card_text(item: WorkspaceCharacterRecord) -> str:
    return (
        "<b>✏️ Карточка персонажа</b>\n\n"
        f"Имя: <b>{escape(item.name)}</b>\n"
        f"ID: <code>{item.id}</code>\n"
        f"Категория: <b>{escape(item.category or 'не выбрана')}</b>\n"
        f"Вселенная: <b>{escape(item.universe or 'не выбрана')}</b>\n"
        f"Материалов: <b>{item.media_count}</b>\n\n"
        f"<b>Истории</b>\n{_story_lines(item)}"
    )


def _card_keyboard(item: WorkspaceCharacterRecord) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📁 Категория",
                    callback_data=_cb(
                        "categories",
                        workspace_id=item.workspace_id,
                        character_id=item.id,
                    ),
                ),
                InlineKeyboardButton(
                    text="🎭 Вселенная",
                    callback_data=_cb(
                        "universes",
                        workspace_id=item.workspace_id,
                        character_id=item.id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📖 Истории",
                    callback_data=_cb(
                        "stories",
                        workspace_id=item.workspace_id,
                        character_id=item.id,
                    ),
                ),
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=_cb(
                        "card",
                        workspace_id=item.workspace_id,
                        character_id=item.id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✖ Закрыть",
                    callback_data=_cb(
                        "close",
                        workspace_id=item.workspace_id,
                        character_id=item.id,
                    ),
                )
            ],
        ]
    )


async def _category_keyboard(
    database: Database,
    *,
    item: WorkspaceCharacterRecord,
) -> InlineKeyboardMarkup:
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT id, key, label, emoji
            FROM workspace_categories
            WHERE workspace_id = $1::BIGINT
              AND is_enabled
            ORDER BY sort_order, label, id
            """,
            int(item.workspace_id),
        )
    buttons = [
        InlineKeyboardButton(
            text=compact_button_text(
                f"{'✅ ' if item.category == str(row['key']) else ''}"
                f"{row['emoji']} {row['label']}"
            ),
            callback_data=_cb(
                "setcat",
                workspace_id=item.workspace_id,
                character_id=item.id,
                item_id=int(row["id"]),
            ),
        )
        for row in rows
    ]
    buttons.append(
        InlineKeyboardButton(
            text="🗂 Без категории",
            callback_data=_cb(
                "clearcat",
                workspace_id=item.workspace_id,
                character_id=item.id,
            ),
        )
    )
    rows_out = two_column_rows(buttons)
    rows_out.append(
        [
            InlineKeyboardButton(
                text="↩️ Карточка",
                callback_data=_cb(
                    "card",
                    workspace_id=item.workspace_id,
                    character_id=item.id,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows_out)


async def _universe_keyboard(
    database: Database,
    *,
    item: WorkspaceCharacterRecord,
) -> InlineKeyboardMarkup:
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT id, key, label, emoji, requires_story
            FROM workspace_universes
            WHERE workspace_id = $1::BIGINT
              AND is_enabled
            ORDER BY sort_order, label, id
            """,
            int(item.workspace_id),
        )
    buttons = [
        InlineKeyboardButton(
            text=compact_button_text(
                f"{'✅ ' if item.universe == str(row['key']) else ''}"
                f"{row['emoji']} {row['label']}"
                f"{' · 📖' if row['requires_story'] else ''}"
            ),
            callback_data=_cb(
                "setuni",
                workspace_id=item.workspace_id,
                character_id=item.id,
                item_id=int(row["id"]),
            ),
        )
        for row in rows
    ]
    buttons.append(
        InlineKeyboardButton(
            text="🌐 Без вселенной",
            callback_data=_cb(
                "clearuni",
                workspace_id=item.workspace_id,
                character_id=item.id,
            ),
        )
    )
    rows_out = two_column_rows(buttons)
    rows_out.append(
        [
            InlineKeyboardButton(
                text="↩️ Карточка",
                callback_data=_cb(
                    "card",
                    workspace_id=item.workspace_id,
                    character_id=item.id,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows_out)


async def _story_keyboard(
    database: Database,
    *,
    item: WorkspaceCharacterRecord,
) -> InlineKeyboardMarkup:
    if not item.universe:
        raise ValueError("Сначала выберите вселенную персонажа.")
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT id, short_label, title
            FROM workspace_stories
            WHERE workspace_id = $1::BIGINT
              AND universe_key = $2::VARCHAR
              AND is_enabled
            ORDER BY sort_order, title, id
            """,
            int(item.workspace_id),
            item.universe,
        )
    selected = {story.id for story in item.stories}
    rows_out = [
        [
            InlineKeyboardButton(
                text=compact_button_text(
                    f"{'✅' if int(row['id']) in selected else '➕'} "
                    f"{row['short_label']} · {row['title']}"
                ),
                callback_data=_cb(
                    "togglestory",
                    workspace_id=item.workspace_id,
                    character_id=item.id,
                    item_id=int(row["id"]),
                ),
            )
        ]
        for row in rows
    ]
    if not rows_out:
        rows_out.append(
            [
                InlineKeyboardButton(
                    text="Историй в этой вселенной нет",
                    callback_data=_cb(
                        "noop",
                        workspace_id=item.workspace_id,
                        character_id=item.id,
                    ),
                )
            ]
        )
    rows_out.append(
        [
            InlineKeyboardButton(
                text="↩️ Карточка",
                callback_data=_cb(
                    "card",
                    workspace_id=item.workspace_id,
                    character_id=item.id,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows_out)


async def _load_checked(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
) -> WorkspaceCharacterRecord:
    item = await load_workspace_character(
        database,
        workspace_id=workspace_id,
        character_id=character_id,
    )
    if item is None:
        raise ValueError("Персонаж не найден в активном пространстве.")
    return item


async def _edit(
    callback: CallbackQuery,
    *,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                raise
    await callback.answer()


async def handle_workspace_character_editor_command(
    message: Message,
    command: CommandObject,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    try:
        character_id = int((command.args or "").strip())
    except ValueError:
        await message.answer("Использование: <code>/wcharacter ID</code>")
        return
    try:
        workspace = await workspace_service.resolve_active_workspace(
            user_id=user_id,
            global_owner=_is_global_owner(user_id),
        )
        if workspace.id == DEFAULT_WORKSPACE_ID:
            raise WorkspaceAccessError(
                "Для системного Velvet используйте существующую карточку персонажа."
            )
        await _require_editor(
            database=database,
            workspace_service=workspace_service,
            workspace_id=workspace.id,
            user_id=user_id,
        )
        item = await _load_checked(
            database,
            workspace_id=workspace.id,
            character_id=character_id,
        )
    except (WorkspaceAccessError, ValueError) as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(_card_text(item), reply_markup=_card_keyboard(item))


async def handle_workspace_character_editor_callback(
    callback: CallbackQuery,
    callback_data: WorkspaceCharacterEditCallback,
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
        await workspace_service.set_active_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=user_id,
            global_owner=_is_global_owner(user_id),
        )
        await _require_editor(
            database=database,
            workspace_service=workspace_service,
            workspace_id=callback_data.workspace_id,
            user_id=user_id,
        )
        item = await _load_checked(
            database,
            workspace_id=callback_data.workspace_id,
            character_id=callback_data.character_id,
        )
        action = callback_data.action
        if action == "setcat":
            category = await _taxonomy_value(
                database,
                workspace_id=item.workspace_id,
                table="workspace_categories",
                item_id=callback_data.item_id,
            )
            item = await set_workspace_character_category(
                database,
                workspace_id=item.workspace_id,
                character_id=item.id,
                category=category,
            )
            action = "card"
        elif action == "clearcat":
            item = await set_workspace_character_category(
                database,
                workspace_id=item.workspace_id,
                character_id=item.id,
                category=None,
            )
            action = "card"
        elif action == "setuni":
            universe = await _taxonomy_value(
                database,
                workspace_id=item.workspace_id,
                table="workspace_universes",
                item_id=callback_data.item_id,
            )
            item = await set_workspace_character_universe(
                database,
                workspace_id=item.workspace_id,
                character_id=item.id,
                universe=universe,
            )
            action = "card"
        elif action == "clearuni":
            item = await set_workspace_character_universe(
                database,
                workspace_id=item.workspace_id,
                character_id=item.id,
                universe=None,
            )
            action = "card"
        elif action == "togglestory":
            await toggle_workspace_character_story(
                database,
                workspace_id=item.workspace_id,
                character_id=item.id,
                story_id=callback_data.item_id,
                assigned_by_user_id=user_id,
            )
            item = await _load_checked(
                database,
                workspace_id=item.workspace_id,
                character_id=item.id,
            )
            action = "stories"

        if action == "card":
            await _edit(callback, text=_card_text(item), keyboard=_card_keyboard(item))
        elif action == "categories":
            await _edit(
                callback,
                text=f"<b>📁 Категория · {escape(item.name)}</b>",
                keyboard=await _category_keyboard(database, item=item),
            )
        elif action == "universes":
            await _edit(
                callback,
                text=f"<b>🎭 Вселенная · {escape(item.name)}</b>",
                keyboard=await _universe_keyboard(database, item=item),
            )
        elif action == "stories":
            await _edit(
                callback,
                text=f"<b>📖 Истории · {escape(item.name)}</b>",
                keyboard=await _story_keyboard(database, item=item),
            )
        else:
            await callback.answer("Неизвестное действие.", show_alert=True)
    except (WorkspaceAccessError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)


router.message.register(
    handle_workspace_character_editor_command,
    Command("wcharacter"),
)
router.callback_query.register(
    handle_workspace_character_editor_callback,
    WorkspaceCharacterEditCallback.filter(),
)

__all__ = ("router",)
