from __future__ import annotations

from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import normalize_emoji, normalize_taxonomy_label
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.workspace_ui import workspace_callback


router = Router(name=__name__)


class WorkspaceTaxonomyAdminCallback(CallbackData, prefix="wtax"):
    action: str
    workspace_id: int
    item_type: str = ""
    item_id: int = 0


class WorkspaceTaxonomyAdminForm(StatesGroup):
    waiting_label = State()
    waiting_emoji = State()


def taxonomy_admin_callback(
    action: str,
    *,
    workspace_id: int,
    item_type: str = "",
    item_id: int = 0,
) -> str:
    return WorkspaceTaxonomyAdminCallback(
        action=action,
        workspace_id=int(workspace_id),
        item_type=item_type,
        item_id=int(item_id),
    ).pack()


def _global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


def _kind_label(item_type: str) -> str:
    return {
        "category": "Категория",
        "universe": "Вселенная",
        "story": "История",
    }.get(item_type, "Элемент")


def _item_select(item_type: str) -> str:
    if item_type == "category":
        return """
            SELECT id, key, label AS name, emoji, is_enabled,
                   NULL::VARCHAR AS universe_key
            FROM workspace_categories
            WHERE workspace_id = $1::BIGINT AND id = $2::BIGINT
        """
    if item_type == "universe":
        return """
            SELECT id, key, label AS name, emoji, is_enabled,
                   NULL::VARCHAR AS universe_key
            FROM workspace_universes
            WHERE workspace_id = $1::BIGINT AND id = $2::BIGINT
        """
    if item_type == "story":
        return """
            SELECT id, key, title AS name, emoji, is_enabled, universe_key
            FROM workspace_stories
            WHERE workspace_id = $1::BIGINT AND id = $2::BIGINT
        """
    raise ValueError("Неизвестный тип структуры.")


async def _require_workspace(
    workspace_service: WorkspaceService,
    *,
    workspace_id: int,
    user_id: int,
) -> Workspace:
    workspace = await workspace_service.set_active_workspace(
        workspace_id=int(workspace_id),
        user_id=int(user_id),
        global_owner=_global_owner(user_id),
    )
    if workspace.is_system:
        raise WorkspaceAccessError(
            "Системная структура Velvet редактируется отдельными инструментами."
        )
    await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=int(user_id),
        minimum_role="editor",
        global_owner=_global_owner(user_id),
    )
    return workspace


async def _require_taxonomy_enabled(database: Database, workspace_id: int) -> None:
    async with database.acquire() as connection:
        enabled = await connection.fetchval(
            """
            SELECT is_allowed AND is_enabled
            FROM workspace_modules
            WHERE workspace_id = $1::BIGINT
              AND module_key = 'taxonomy'
            """,
            int(workspace_id),
        )
    if not enabled:
        raise WorkspaceAccessError("Модуль категорий и вселенных выключен.")


async def _active_personal_workspace(
    workspace_service: WorkspaceService,
    *,
    user_id: int,
) -> Workspace:
    workspace = await workspace_service.resolve_active_workspace(
        user_id=int(user_id),
        global_owner=_global_owner(user_id),
    )
    return await _require_workspace(
        workspace_service,
        workspace_id=workspace.id,
        user_id=user_id,
    )


async def _rows(database: Database, workspace_id: int, item_type: str) -> Any:
    async with database.acquire() as connection:
        if item_type == "category":
            return await connection.fetch(
                """
                SELECT id, key, label AS name, emoji, is_enabled
                FROM workspace_categories
                WHERE workspace_id = $1::BIGINT
                ORDER BY is_enabled DESC, sort_order, label, id
                """,
                int(workspace_id),
            )
        if item_type == "universe":
            return await connection.fetch(
                """
                SELECT id, key, label AS name, emoji, is_enabled
                FROM workspace_universes
                WHERE workspace_id = $1::BIGINT
                ORDER BY is_enabled DESC, sort_order, label, id
                """,
                int(workspace_id),
            )
        if item_type == "story":
            return await connection.fetch(
                """
                SELECT id, key, title AS name, emoji, is_enabled, universe_key
                FROM workspace_stories
                WHERE workspace_id = $1::BIGINT
                ORDER BY universe_key, is_enabled DESC, sort_order, title, id
                """,
                int(workspace_id),
            )
    raise ValueError("Неизвестный тип структуры.")


async def _item(
    database: Database,
    workspace_id: int,
    item_type: str,
    item_id: int,
) -> Any:
    async with database.acquire() as connection:
        return await connection.fetchrow(
            _item_select(item_type),
            int(workspace_id),
            int(item_id),
        )


def _manage_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📁 Категории",
                    callback_data=taxonomy_admin_callback(
                        "list", workspace_id=workspace_id, item_type="category"
                    ),
                ),
                InlineKeyboardButton(
                    text="🎭 Вселенные",
                    callback_data=taxonomy_admin_callback(
                        "list", workspace_id=workspace_id, item_type="universe"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📖 Истории",
                    callback_data=taxonomy_admin_callback(
                        "list", workspace_id=workspace_id, item_type="story"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Структура архива",
                    callback_data=workspace_callback(
                        "taxonomy", workspace_id=workspace_id
                    ),
                )
            ],
        ]
    )


async def _send_or_edit(
    event: Message | CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    if isinstance(event, CallbackQuery):
        if isinstance(event.message, Message):
            try:
                await event.message.edit_text(text, reply_markup=keyboard)
            except TelegramBadRequest as error:
                if "message is not modified" not in str(error).casefold():
                    await event.message.answer(text, reply_markup=keyboard)
        await event.answer()
        return
    await event.answer(text, reply_markup=keyboard)


async def _render_manage(event: Message | CallbackQuery, workspace: Workspace) -> None:
    await _send_or_edit(
        event,
        (
            f"<b>🛠 Структура · {escape(workspace.name)}</b>\n\n"
            "Здесь можно изменить название и emoji либо удалить категорию, "
            "вселенную или историю. Внутренний ключ остаётся стабильным, поэтому "
            "карточки не теряют связь из-за обычного переименования."
        ),
        _manage_keyboard(workspace.id),
    )


async def _render_list(
    event: Message | CallbackQuery,
    *,
    database: Database,
    workspace_id: int,
    item_type: str,
) -> None:
    items = await _rows(database, workspace_id, item_type)
    rows: list[list[InlineKeyboardButton]] = []
    for row in items[:80]:
        suffix = "" if bool(row["is_enabled"]) else " · выключено"
        universe = f" · {row['universe_key']}" if item_type == "story" else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{row['emoji']} {row['name']}{universe}{suffix}"[:64],
                    callback_data=taxonomy_admin_callback(
                        "item",
                        workspace_id=workspace_id,
                        item_type=item_type,
                        item_id=int(row["id"]),
                    ),
                )
            ]
        )
    if not rows:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Пока пусто",
                    callback_data=taxonomy_admin_callback(
                        "manage", workspace_id=workspace_id
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Управление структурой",
                callback_data=taxonomy_admin_callback(
                    "manage", workspace_id=workspace_id
                ),
            )
        ]
    )
    await _send_or_edit(
        event,
        f"<b>{escape(_kind_label(item_type))}</b>\n\nВыберите элемент для изменения.",
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _render_item(
    event: Message | CallbackQuery,
    *,
    database: Database,
    workspace_id: int,
    item_type: str,
    item_id: int,
) -> None:
    row = await _item(database, workspace_id, item_type, item_id)
    if row is None:
        raise ValueError("Элемент уже удалён.")
    extra = (
        f"\nВселенная: <code>{escape(str(row['universe_key']))}</code>"
        if item_type == "story"
        else ""
    )
    text = (
        f"<b>{escape(_kind_label(item_type))}</b>\n\n"
        f"Название: <b>{escape(str(row['name']))}</b>\n"
        f"Emoji: <b>{escape(str(row['emoji']))}</b>\n"
        f"Ключ: <code>{escape(str(row['key']))}</code>{extra}"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Название",
                    callback_data=taxonomy_admin_callback(
                        "rename",
                        workspace_id=workspace_id,
                        item_type=item_type,
                        item_id=item_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="😀 Emoji",
                    callback_data=taxonomy_admin_callback(
                        "emoji",
                        workspace_id=workspace_id,
                        item_type=item_type,
                        item_id=item_id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=taxonomy_admin_callback(
                        "delete",
                        workspace_id=workspace_id,
                        item_type=item_type,
                        item_id=item_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К списку",
                    callback_data=taxonomy_admin_callback(
                        "list", workspace_id=workspace_id, item_type=item_type
                    ),
                )
            ],
        ]
    )
    await _send_or_edit(event, text, keyboard)


async def _delete_item(
    database: Database,
    *,
    workspace_id: int,
    item_type: str,
    item_id: int,
) -> bool:
    async with database.acquire() as connection:
        async with connection.transaction():
            row = await connection.fetchrow(
                _item_select(item_type),
                int(workspace_id),
                int(item_id),
            )
            if row is None:
                return False
            key = str(row["key"])
            if item_type == "category":
                await connection.execute(
                    "UPDATE characters SET category = NULL "
                    "WHERE workspace_id = $1 AND category = $2",
                    int(workspace_id),
                    key,
                )
                result = await connection.execute(
                    "DELETE FROM workspace_categories "
                    "WHERE workspace_id = $1 AND id = $2",
                    int(workspace_id),
                    int(item_id),
                )
            elif item_type == "universe":
                await connection.execute(
                    """
                    UPDATE characters
                    SET universe = NULL, story_id = NULL
                    WHERE workspace_id = $1 AND universe = $2
                    """,
                    int(workspace_id),
                    key,
                )
                result = await connection.execute(
                    "DELETE FROM workspace_universes "
                    "WHERE workspace_id = $1 AND id = $2",
                    int(workspace_id),
                    int(item_id),
                )
            elif item_type == "story":
                result = await connection.execute(
                    "DELETE FROM workspace_stories "
                    "WHERE workspace_id = $1 AND id = $2",
                    int(workspace_id),
                    int(item_id),
                )
            else:
                raise ValueError("Неизвестный тип структуры.")
    return result != "DELETE 0"


async def _update_item(
    database: Database,
    *,
    workspace_id: int,
    item_type: str,
    item_id: int,
    field: str,
    value: str,
) -> bool:
    if field == "name":
        column = "title" if item_type == "story" else "label"
        cleaned = normalize_taxonomy_label(
            value,
            limit=192 if item_type == "story" else 96,
        )
    elif field == "emoji":
        column = "emoji"
        cleaned = normalize_emoji(
            value,
            fallback="📖" if item_type == "story" else "📁",
        )
    else:
        raise ValueError("Неизвестное поле структуры.")
    table = {
        "category": "workspace_categories",
        "universe": "workspace_universes",
        "story": "workspace_stories",
    }.get(item_type)
    if table is None:
        raise ValueError("Неизвестный тип структуры.")
    async with database.acquire() as connection:
        result = await connection.execute(
            f"UPDATE {table} SET {column} = $3::VARCHAR, updated_at = NOW() "
            "WHERE workspace_id = $1::BIGINT AND id = $2::BIGINT",
            int(workspace_id),
            int(item_id),
            cleaned,
        )
    return result != "UPDATE 0"


@router.message(Command("myarchive", "archive_shortcuts"))
async def handle_personal_archive_shortcuts(
    message: Message,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    if message.from_user is None:
        return
    try:
        workspace = await _active_personal_workspace(
            workspace_service,
            user_id=message.from_user.id,
        )
        await _require_taxonomy_enabled(database, workspace.id)
    except WorkspaceAccessError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(
        f"<b>⚡ {escape(workspace.name)} · быстрые команды</b>\n\n"
        "Сохранить материалы пакетно:\n"
        "<code>/save Имя или алиас персонажа</code>\n\n"
        "Открыть референсы:\n"
        "<code>/refs Имя или алиас персонажа</code>\n\n"
        "Добавлять референсы подряд:\n"
        "<code>/refadd Имя или алиас персонажа</code>\n\n"
        "Завершить загрузку: <code>/refdone</code>\n"
        "Управление структурой: <code>/taxonomy_manage</code>"
    )


@router.message(Command("taxonomy_manage", "structure_manage"))
async def handle_taxonomy_manage_command(
    message: Message,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    if message.from_user is None:
        return
    try:
        workspace = await _active_personal_workspace(
            workspace_service,
            user_id=message.from_user.id,
        )
        await _require_taxonomy_enabled(database, workspace.id)
    except WorkspaceAccessError as error:
        await message.answer(escape(str(error)))
        return
    await _render_manage(message, workspace)


async def handle_taxonomy_admin_callback(
    callback: CallbackQuery,
    callback_data: WorkspaceTaxonomyAdminCallback,
    state: FSMContext,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    try:
        workspace = await _require_workspace(
            workspace_service,
            workspace_id=callback_data.workspace_id,
            user_id=callback.from_user.id,
        )
        await _require_taxonomy_enabled(database, workspace.id)
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    try:
        if callback_data.action == "manage":
            await state.clear()
            await _render_manage(callback, workspace)
            return
        if callback_data.action == "list":
            await state.clear()
            await _render_list(
                callback,
                database=database,
                workspace_id=workspace.id,
                item_type=callback_data.item_type,
            )
            return
        if callback_data.action == "item":
            await state.clear()
            await _render_item(
                callback,
                database=database,
                workspace_id=workspace.id,
                item_type=callback_data.item_type,
                item_id=callback_data.item_id,
            )
            return
        if callback_data.action in {"rename", "emoji"}:
            await state.set_state(
                WorkspaceTaxonomyAdminForm.waiting_label
                if callback_data.action == "rename"
                else WorkspaceTaxonomyAdminForm.waiting_emoji
            )
            await state.update_data(
                workspace_id=workspace.id,
                item_type=callback_data.item_type,
                item_id=callback_data.item_id,
            )
            prompt = (
                "Отправьте новое название одним сообщением."
                if callback_data.action == "rename"
                else "Отправьте новый emoji или короткий значок одним сообщением."
            )
            if isinstance(callback.message, Message):
                await callback.message.answer(prompt)
            await callback.answer()
            return
        if callback_data.action == "delete":
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Да, удалить",
                            callback_data=taxonomy_admin_callback(
                                "deleteok",
                                workspace_id=workspace.id,
                                item_type=callback_data.item_type,
                                item_id=callback_data.item_id,
                            ),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Отмена",
                            callback_data=taxonomy_admin_callback(
                                "item",
                                workspace_id=workspace.id,
                                item_type=callback_data.item_type,
                                item_id=callback_data.item_id,
                            ),
                        )
                    ],
                ]
            )
            await _send_or_edit(
                callback,
                "<b>Удалить элемент?</b>\n\n"
                "Связь будет снята с персонажей. При удалении вселенной её истории "
                "также удаляются из этого личного архива.",
                keyboard,
            )
            return
        if callback_data.action == "deleteok":
            await _delete_item(
                database,
                workspace_id=workspace.id,
                item_type=callback_data.item_type,
                item_id=callback_data.item_id,
            )
            await _render_list(
                callback,
                database=database,
                workspace_id=workspace.id,
                item_type=callback_data.item_type,
            )
            return
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer("Неизвестное действие.", show_alert=True)


@router.message(WorkspaceTaxonomyAdminForm.waiting_label, F.text)
@router.message(WorkspaceTaxonomyAdminForm.waiting_emoji, F.text)
async def handle_taxonomy_admin_form(
    message: Message,
    state: FSMContext,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    item_type = str(data.get("item_type") or "")
    item_id = int(data.get("item_id") or 0)
    current_state = await state.get_state()
    field = (
        "emoji"
        if current_state == WorkspaceTaxonomyAdminForm.waiting_emoji.state
        else "name"
    )
    try:
        await _require_workspace(
            workspace_service,
            workspace_id=workspace_id,
            user_id=message.from_user.id,
        )
        await _require_taxonomy_enabled(database, workspace_id)
        updated = await _update_item(
            database,
            workspace_id=workspace_id,
            item_type=item_type,
            item_id=item_id,
            field=field,
            value=message.text or "",
        )
    except (ValueError, WorkspaceAccessError) as error:
        await message.answer(f"❌ {escape(str(error))}")
        return
    await state.clear()
    if not updated:
        await message.answer("Элемент уже удалён.")
        return
    await message.answer(
        "✅ Сохранено.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Открыть элемент",
                        callback_data=taxonomy_admin_callback(
                            "item",
                            workspace_id=workspace_id,
                            item_type=item_type,
                            item_id=item_id,
                        ),
                    )
                ]
            ]
        ),
    )


router.callback_query.register(
    handle_taxonomy_admin_callback,
    WorkspaceTaxonomyAdminCallback.filter(),
)


__all__ = (
    "WorkspaceTaxonomyAdminCallback",
    "router",
    "taxonomy_admin_callback",
)
