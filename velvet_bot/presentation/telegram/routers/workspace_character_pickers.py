from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import cast

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.character_management import (
    WorkspaceCharacterRecord,
    load_workspace_character,
    set_workspace_character_category,
    set_workspace_character_universe,
    toggle_workspace_character_story,
)
from velvet_bot.domains.workspaces.models import WorkspaceRole
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.routers.workspace_character_management import WorkspaceForm
from velvet_bot.presentation.telegram.routers.workspace_guided_ui import guided_workspace_callback
from velvet_bot.workspace_ui import WorkspaceCallback, workspace_callback

router = Router(name=__name__)

_CHARACTER_PAGE_SIZE = 8
_OPTION_PAGE_SIZE = 8


class WorkspaceCharacterPickerCallback(CallbackData, prefix="wch"):
    action: str
    workspace_id: int
    character_id: int = 0
    item_id: int = 0
    page: int = 0


@dataclass(frozen=True, slots=True)
class CharacterPickerItem:
    id: int
    name: str
    category_label: str | None
    category_emoji: str | None
    universe_label: str | None
    universe_emoji: str | None


@dataclass(frozen=True, slots=True)
class CharacterPickerPage:
    items: tuple[CharacterPickerItem, ...]
    page: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + _CHARACTER_PAGE_SIZE - 1) // _CHARACTER_PAGE_SIZE)


@dataclass(frozen=True, slots=True)
class TaxonomyPickerItem:
    id: int
    key: str
    label: str
    emoji: str
    selected: bool = False
    primary: bool = False
    requires_story: bool = False


@dataclass(frozen=True, slots=True)
class TaxonomyPickerPage:
    items: tuple[TaxonomyPickerItem, ...]
    page: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + _OPTION_PAGE_SIZE - 1) // _OPTION_PAGE_SIZE)


def _callback(
    action: str,
    *,
    workspace_id: int,
    character_id: int = 0,
    item_id: int = 0,
    page: int = 0,
) -> str:
    return WorkspaceCharacterPickerCallback(
        action=action,
        workspace_id=int(workspace_id),
        character_id=int(character_id),
        item_id=int(item_id),
        page=max(0, int(page)),
    ).pack()


async def _module_enabled(database: Database, *, workspace_id: int) -> bool:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT is_allowed AND is_enabled
            FROM workspace_modules
            WHERE workspace_id = $1::BIGINT
              AND module_key = 'characters'
            """,
            int(workspace_id),
        )
    return bool(value)


async def _require_access(
    *,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_id: int,
    user_id: int,
) -> str:
    workspace = await workspace_service.set_active_workspace(
        workspace_id=int(workspace_id),
        user_id=int(user_id),
        global_owner=int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID,
    )
    if workspace.is_system:
        raise WorkspaceAccessError(
            "Системный Velvet использует существующий раздел персонажей."
        )
    await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=int(user_id),
        minimum_role=cast(WorkspaceRole, "editor"),
        global_owner=int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID,
    )
    if not await _module_enabled(database, workspace_id=workspace.id):
        raise WorkspaceAccessError("Модуль персонажей выключен или не разрешён Стэл.")
    return workspace.name


async def _load_character_page(
    database: Database,
    *,
    workspace_id: int,
    page: int,
) -> CharacterPickerPage:
    safe_page = max(0, int(page))
    async with database.acquire() as connection:
        total = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM characters WHERE workspace_id = $1::BIGINT",
                int(workspace_id),
            )
            or 0
        )
        total_pages = max(1, (total + _CHARACTER_PAGE_SIZE - 1) // _CHARACTER_PAGE_SIZE)
        normalized_page = min(safe_page, total_pages - 1)
        rows = await connection.fetch(
            """
            SELECT
                character.id,
                character.name,
                category.label AS category_label,
                category.emoji AS category_emoji,
                universe.label AS universe_label,
                universe.emoji AS universe_emoji
            FROM characters AS character
            LEFT JOIN workspace_categories AS category
              ON category.workspace_id = character.workspace_id
             AND category.key = character.category
            LEFT JOIN workspace_universes AS universe
              ON universe.workspace_id = character.workspace_id
             AND universe.key = character.universe
            WHERE character.workspace_id = $1::BIGINT
            ORDER BY character.normalized_name, character.id
            OFFSET $2::INTEGER
            LIMIT $3::INTEGER
            """,
            int(workspace_id),
            normalized_page * _CHARACTER_PAGE_SIZE,
            _CHARACTER_PAGE_SIZE,
        )
    return CharacterPickerPage(
        items=tuple(
            CharacterPickerItem(
                id=int(row["id"]),
                name=str(row["name"]),
                category_label=(
                    str(row["category_label"])
                    if row["category_label"] is not None
                    else None
                ),
                category_emoji=(
                    str(row["category_emoji"])
                    if row["category_emoji"] is not None
                    else None
                ),
                universe_label=(
                    str(row["universe_label"])
                    if row["universe_label"] is not None
                    else None
                ),
                universe_emoji=(
                    str(row["universe_emoji"])
                    if row["universe_emoji"] is not None
                    else None
                ),
            )
            for row in rows
        ),
        page=normalized_page,
        total_items=total,
    )


def _character_list_text(workspace_name: str, page: CharacterPickerPage) -> str:
    return (
        f"<b>👥 Персонажи · {escape(workspace_name)}</b>\n\n"
        f"Персонажей: <b>{page.total_items}</b>\n"
        f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>\n\n"
        "Выберите персонажа. Из карточки можно сохранить материал, изменить имя, "
        "ветку, промт и алиас, а также назначить категорию, вселенную и истории."
    )



def _character_button_text(item: CharacterPickerItem) -> str:
    category = (
        f"{item.category_emoji or '🗂'} {item.category_label}"
        if item.category_label
        else "➖ без категории"
    )
    universe = (
        f"{item.universe_emoji or '🌌'} {item.universe_label}"
        if item.universe_label
        else "без вселенной"
    )
    return f"👤 {item.name} · {category} · {universe}"[:60]


def _character_list_keyboard(
    *,
    workspace_id: int,
    page: CharacterPickerPage,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_character_button_text(item),
                callback_data=_callback(
                    "card",
                    workspace_id=workspace_id,
                    character_id=item.id,
                    page=page.page,
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
                    callback_data=_callback(
                        "list",
                        workspace_id=workspace_id,
                        page=(page.page - 1) % page.total_pages,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1} / {page.total_pages}",
                    callback_data=_callback(
                        "noop",
                        workspace_id=workspace_id,
                        page=page.page,
                    ),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_callback(
                        "list",
                        workspace_id=workspace_id,
                        page=(page.page + 1) % page.total_pages,
                    ),
                ),
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="➕ Создать персонажа",
                    callback_data=guided_workspace_callback(
                        "cnew",
                        workspace_id=workspace_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="💾 Сохранить",
                    callback_data=guided_workspace_callback(
                        "savepick",
                        workspace_id=workspace_id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Моё пространство",
                    callback_data=workspace_callback("home", workspace_id=workspace_id),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)



async def build_character_module_keyboard(
    database: Database,
    *,
    workspace_id: int,
    page: int = 0,
) -> InlineKeyboardMarkup:
    return _character_list_keyboard(
        workspace_id=workspace_id,
        page=await _load_character_page(
            database,
            workspace_id=workspace_id,
            page=page,
        ),
    )


async def _load_card_details(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
):
    async with database.acquire() as connection:
        return await connection.fetchrow(
            """
            SELECT
                category.label AS category_label,
                category.emoji AS category_emoji,
                universe.label AS universe_label,
                universe.emoji AS universe_emoji,
                universe.requires_story,
                COUNT(media.media_id) AS media_count
            FROM characters AS character
            LEFT JOIN workspace_categories AS category
              ON category.workspace_id = character.workspace_id
             AND category.key = character.category
            LEFT JOIN workspace_universes AS universe
              ON universe.workspace_id = character.workspace_id
             AND universe.key = character.universe
            LEFT JOIN character_media AS media ON media.character_id = character.id
            WHERE character.workspace_id = $1::BIGINT
              AND character.id = $2::BIGINT
            GROUP BY category.id, universe.id
            """,
            int(workspace_id),
            int(character_id),
        )


async def _card_text(
    database: Database,
    *,
    workspace_id: int,
    character: WorkspaceCharacterRecord,
) -> str:
    details = await _load_card_details(
        database,
        workspace_id=workspace_id,
        character_id=character.id,
    )
    if details is None:
        raise ValueError("Персонаж не найден в этом архиве.")
    category = (
        f"{escape(str(details['category_emoji']))} "
        f"{escape(str(details['category_label']))}"
        if details["category_label"] is not None
        else "не выбрана"
    )
    universe = (
        f"{escape(str(details['universe_emoji']))} "
        f"{escape(str(details['universe_label']))}"
        if details["universe_label"] is not None
        else "не выбрана"
    )
    lines = [
        "<b>👤 Карточка персонажа</b>",
        "",
        f"Имя: <b>{escape(character.name)}</b>",
        f"ID: <code>{character.id}</code>",
        f"Категория: <b>{category}</b>",
        f"Вселенная: <b>{universe}</b>",
        f"Материалов: <b>{int(details['media_count'] or 0)}</b>",
    ]
    if bool(details["requires_story"]):
        lines.append("История для этой вселенной: <b>обязательна</b>")
    lines.extend(["", "<b>Истории</b>"])
    if character.stories:
        for story in character.stories:
            marker = "⭐" if story.is_primary else "✅"
            lines.append(
                f"{marker} {escape(story.short_label)} · {escape(story.title)}"
            )
    else:
        lines.append("Не назначены.")
    manual_aliases = [item for item in character.aliases if item.source != "name"]
    lines.extend(["", "<b>Алиасы</b>"])
    if manual_aliases:
        lines.extend(f"• {escape(item.alias)}" for item in manual_aliases)
    else:
        lines.append("Не добавлены.")
    lines.extend(
        [
            "",
            (
                f'<a href="{escape(character.prompt_post_url, quote=True)}">Открыть промт</a>'
                if character.prompt_post_url
                else "Промт не назначен."
            ),
            (
                f'<a href="{escape(character.archive_topic_url, quote=True)}">Открыть тему Telegram</a>'
                if character.archive_topic_url
                else "Тема Telegram не назначена."
            ),
        ]
    )
    return "\n".join(lines)


def _card_keyboard(
    *,
    workspace_id: int,
    character_id: int,
    list_page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💾 Сохранить",
                    callback_data=guided_workspace_callback(
                        "save",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=list_page,
                    ),
                ),
                InlineKeyboardButton(
                    text="✏️ Имя",
                    callback_data=guided_workspace_callback(
                        "rename",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=list_page,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔗 Ветка",
                    callback_data=guided_workspace_callback(
                        "topicedit",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=list_page,
                    ),
                ),
                InlineKeyboardButton(
                    text="📝 Промт",
                    callback_data=guided_workspace_callback(
                        "prompt",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=list_page,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏷 Добавить алиас",
                    callback_data=guided_workspace_callback(
                        "alias",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=list_page,
                    ),
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=guided_workspace_callback(
                        "deleteask",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=list_page,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗂 Категория",
                    callback_data=_callback(
                        "cat",
                        workspace_id=workspace_id,
                        character_id=character_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="🌌 Вселенная",
                    callback_data=_callback(
                        "uni",
                        workspace_id=workspace_id,
                        character_id=character_id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📖 Истории",
                    callback_data=_callback(
                        "story",
                        workspace_id=workspace_id,
                        character_id=character_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=_callback(
                        "card",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=list_page,
                    ),
                ),
                InlineKeyboardButton(
                    text="↩️ К списку",
                    callback_data=_callback(
                        "list",
                        workspace_id=workspace_id,
                        page=list_page,
                    ),
                ),
            ],
        ]
    )



async def _load_taxonomy_page(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
    kind: str,
    page: int,
) -> TaxonomyPickerPage:
    if kind not in {"category", "universe", "story"}:
        raise ValueError("Неизвестный тип структуры.")
    safe_page = max(0, int(page))
    async with database.acquire() as connection:
        character = await connection.fetchrow(
            """
            SELECT category, universe
            FROM characters
            WHERE workspace_id = $1::BIGINT AND id = $2::BIGINT
            """,
            int(workspace_id),
            int(character_id),
        )
        if character is None:
            raise ValueError("Персонаж не найден в этом архиве.")
        if kind == "category":
            total = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*) FROM workspace_categories
                    WHERE workspace_id = $1::BIGINT AND is_enabled
                    """,
                    int(workspace_id),
                )
                or 0
            )
            total_pages = max(1, (total + _OPTION_PAGE_SIZE - 1) // _OPTION_PAGE_SIZE)
            normalized_page = min(safe_page, total_pages - 1)
            rows = await connection.fetch(
                """
                SELECT id, key, label, emoji
                FROM workspace_categories
                WHERE workspace_id = $1::BIGINT AND is_enabled
                ORDER BY sort_order, label, id
                OFFSET $2::INTEGER LIMIT $3::INTEGER
                """,
                int(workspace_id),
                normalized_page * _OPTION_PAGE_SIZE,
                _OPTION_PAGE_SIZE,
            )
            items = tuple(
                TaxonomyPickerItem(
                    id=int(row["id"]),
                    key=str(row["key"]),
                    label=str(row["label"]),
                    emoji=str(row["emoji"]),
                    selected=row["key"] == character["category"],
                )
                for row in rows
            )
        elif kind == "universe":
            total = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*) FROM workspace_universes
                    WHERE workspace_id = $1::BIGINT AND is_enabled
                    """,
                    int(workspace_id),
                )
                or 0
            )
            total_pages = max(1, (total + _OPTION_PAGE_SIZE - 1) // _OPTION_PAGE_SIZE)
            normalized_page = min(safe_page, total_pages - 1)
            rows = await connection.fetch(
                """
                SELECT id, key, label, emoji, requires_story
                FROM workspace_universes
                WHERE workspace_id = $1::BIGINT AND is_enabled
                ORDER BY sort_order, label, id
                OFFSET $2::INTEGER LIMIT $3::INTEGER
                """,
                int(workspace_id),
                normalized_page * _OPTION_PAGE_SIZE,
                _OPTION_PAGE_SIZE,
            )
            items = tuple(
                TaxonomyPickerItem(
                    id=int(row["id"]),
                    key=str(row["key"]),
                    label=str(row["label"]),
                    emoji=str(row["emoji"]),
                    selected=row["key"] == character["universe"],
                    requires_story=bool(row["requires_story"]),
                )
                for row in rows
            )
        else:
            if character["universe"] is None:
                raise ValueError("Сначала назначьте персонажу вселенную.")
            total = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*) FROM workspace_stories
                    WHERE workspace_id = $1::BIGINT
                      AND universe_key = $2::VARCHAR
                      AND is_enabled
                    """,
                    int(workspace_id),
                    str(character["universe"]),
                )
                or 0
            )
            total_pages = max(1, (total + _OPTION_PAGE_SIZE - 1) // _OPTION_PAGE_SIZE)
            normalized_page = min(safe_page, total_pages - 1)
            rows = await connection.fetch(
                """
                SELECT
                    story.id,
                    story.key,
                    story.short_label,
                    story.title,
                    link.story_id IS NOT NULL AS selected,
                    COALESCE(link.is_primary, FALSE) AS primary
                FROM workspace_stories AS story
                LEFT JOIN workspace_character_story_links AS link
                  ON link.workspace_id = story.workspace_id
                 AND link.story_id = story.id
                 AND link.character_id = $3::BIGINT
                WHERE story.workspace_id = $1::BIGINT
                  AND story.universe_key = $2::VARCHAR
                  AND story.is_enabled
                ORDER BY story.sort_order, story.title, story.id
                OFFSET $4::INTEGER LIMIT $5::INTEGER
                """,
                int(workspace_id),
                str(character["universe"]),
                int(character_id),
                normalized_page * _OPTION_PAGE_SIZE,
                _OPTION_PAGE_SIZE,
            )
            items = tuple(
                TaxonomyPickerItem(
                    id=int(row["id"]),
                    key=str(row["key"]),
                    label=f"{row['short_label']} · {row['title']}",
                    emoji="📖",
                    selected=bool(row["selected"]),
                    primary=bool(row["primary"]),
                )
                for row in rows
            )
    return TaxonomyPickerPage(
        items=items,
        page=normalized_page,
        total_items=total,
    )


def _taxonomy_text(kind: str, character: WorkspaceCharacterRecord) -> str:
    titles = {
        "category": "🗂 Выберите категорию",
        "universe": "🌌 Выберите вселенную",
        "story": "📖 Выберите истории",
    }
    hint = (
        "Можно назначить несколько историй. Первая выбранная становится основной."
        if kind == "story"
        else "Выбор применяется только внутри текущего пространства."
    )
    return (
        f"<b>{titles[kind]}</b>\n\n"
        f"Персонаж: <b>{escape(character.name)}</b> <code>#{character.id}</code>\n\n"
        f"{hint}"
    )


def _taxonomy_keyboard(
    *,
    workspace_id: int,
    character_id: int,
    kind: str,
    page: TaxonomyPickerPage,
    list_page: int,
) -> InlineKeyboardMarkup:
    action = {"category": "catset", "universe": "uniset", "story": "storyset"}[kind]
    open_action = {"category": "cat", "universe": "uni", "story": "story"}[kind]
    rows: list[list[InlineKeyboardButton]] = []
    if kind in {"category", "universe"}:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Не назначено" if not any(item.selected for item in page.items) else "➖ Не назначено",
                    callback_data=_callback(
                        action,
                        workspace_id=workspace_id,
                        character_id=character_id,
                        item_id=0,
                        page=page.page,
                    ),
                )
            ]
        )
    for item in page.items:
        marker = "⭐" if item.primary else ("✅" if item.selected else item.emoji)
        suffix = " · нужна история" if item.requires_story else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker} {item.label}{suffix}"[:60],
                    callback_data=_callback(
                        action,
                        workspace_id=workspace_id,
                        character_id=character_id,
                        item_id=item.id,
                        page=page.page,
                    ),
                )
            ]
        )
    if page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_callback(
                        open_action,
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=(page.page - 1) % page.total_pages,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1} / {page.total_pages}",
                    callback_data=_callback(
                        "noop",
                        workspace_id=workspace_id,
                        character_id=character_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_callback(
                        open_action,
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=(page.page + 1) % page.total_pages,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К карточке",
                callback_data=_callback(
                    "card",
                    workspace_id=workspace_id,
                    character_id=character_id,
                    page=list_page,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _edit(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    answer: str | None = None,
    show_alert: bool = False,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            await callback.message.answer(text, reply_markup=reply_markup)
    await callback.answer(answer, show_alert=show_alert)


async def _render_list(
    callback: CallbackQuery,
    *,
    database: Database,
    workspace_id: int,
    workspace_name: str,
    page_number: int,
) -> None:
    page = await _load_character_page(
        database,
        workspace_id=workspace_id,
        page=page_number,
    )
    await _edit(
        callback,
        text=_character_list_text(workspace_name, page),
        reply_markup=_character_list_keyboard(workspace_id=workspace_id, page=page),
    )


async def _render_card(
    callback: CallbackQuery,
    *,
    database: Database,
    workspace_id: int,
    character_id: int,
    list_page: int,
    answer: str | None = None,
) -> None:
    character = await load_workspace_character(
        database,
        workspace_id=workspace_id,
        character_id=character_id,
    )
    if character is None:
        raise ValueError("Персонаж не найден в этом архиве.")
    await _edit(
        callback,
        text=await _card_text(
            database,
            workspace_id=workspace_id,
            character=character,
        ),
        reply_markup=_card_keyboard(
            workspace_id=workspace_id,
            character_id=character_id,
            list_page=list_page,
        ),
        answer=answer,
    )


async def _render_taxonomy(
    callback: CallbackQuery,
    *,
    database: Database,
    workspace_id: int,
    character_id: int,
    kind: str,
    page_number: int,
    list_page: int,
    answer: str | None = None,
) -> None:
    character = await load_workspace_character(
        database,
        workspace_id=workspace_id,
        character_id=character_id,
    )
    if character is None:
        raise ValueError("Персонаж не найден в этом архиве.")
    page = await _load_taxonomy_page(
        database,
        workspace_id=workspace_id,
        character_id=character_id,
        kind=kind,
        page=page_number,
    )
    await _edit(
        callback,
        text=_taxonomy_text(kind, character),
        reply_markup=_taxonomy_keyboard(
            workspace_id=workspace_id,
            character_id=character_id,
            kind=kind,
            page=page,
            list_page=list_page,
        ),
        answer=answer,
    )


async def _resolve_category_key(
    database: Database,
    *,
    workspace_id: int,
    item_id: int,
) -> str | None:
    if int(item_id) == 0:
        return None
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT key
            FROM workspace_categories
            WHERE workspace_id = $1::BIGINT
              AND id = $2::BIGINT
              AND is_enabled
            """,
            int(workspace_id),
            int(item_id),
        )
    if value is None:
        raise ValueError("Категория больше недоступна в этом архиве.")
    return str(value)


async def _resolve_universe(
    database: Database,
    *,
    workspace_id: int,
    item_id: int,
) -> tuple[str | None, bool]:
    if int(item_id) == 0:
        return None, False
    async with database.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT key, requires_story
            FROM workspace_universes
            WHERE workspace_id = $1::BIGINT
              AND id = $2::BIGINT
              AND is_enabled
            """,
            int(workspace_id),
            int(item_id),
        )
    if row is None:
        raise ValueError("Вселенная больше недоступна в этом архиве.")
    return str(row["key"]), bool(row["requires_story"])


@router.callback_query(
    WorkspaceCallback.filter((F.action == "module") & (F.module_key == "characters"))
)
async def handle_workspace_character_picker_entry(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    try:
        workspace_name = await _require_access(
            database=database,
            workspace_service=workspace_service,
            workspace_id=callback_data.workspace_id,
            user_id=callback.from_user.id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    # The picker is button-first. Earlier versions silently entered the legacy
    # free-text command mode here, so a failed button left a user trapped in an
    # unrelated FSM state. Opening the picker now also recovers any old state.
    await state.clear()
    await _render_list(
        callback,
        database=database,
        workspace_id=int(callback_data.workspace_id),
        workspace_name=workspace_name,
        page_number=0,
    )


@router.callback_query(WorkspaceCharacterPickerCallback.filter())
async def handle_workspace_character_picker(
    callback: CallbackQuery,
    callback_data: WorkspaceCharacterPickerCallback,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    try:
        workspace_name = await _require_access(
            database=database,
            workspace_service=workspace_service,
            workspace_id=callback_data.workspace_id,
            user_id=callback.from_user.id,
        )
        action = callback_data.action
        if action == "noop":
            await callback.answer()
            return
        if action == "new":
            await callback.answer(
                "Отправьте сообщением: создать Имя персонажа",
                show_alert=True,
            )
            return
        if action == "list":
            await _render_list(
                callback,
                database=database,
                workspace_id=callback_data.workspace_id,
                workspace_name=workspace_name,
                page_number=callback_data.page,
            )
            return
        if action == "card":
            await _render_card(
                callback,
                database=database,
                workspace_id=callback_data.workspace_id,
                character_id=callback_data.character_id,
                list_page=callback_data.page,
            )
            return
        if action in {"cat", "uni", "story"}:
            kind = {"cat": "category", "uni": "universe", "story": "story"}[action]
            await _render_taxonomy(
                callback,
                database=database,
                workspace_id=callback_data.workspace_id,
                character_id=callback_data.character_id,
                kind=kind,
                page_number=callback_data.page,
                list_page=0,
            )
            return
        if action == "catset":
            key = await _resolve_category_key(
                database,
                workspace_id=callback_data.workspace_id,
                item_id=callback_data.item_id,
            )
            await set_workspace_character_category(
                database,
                workspace_id=callback_data.workspace_id,
                character_id=callback_data.character_id,
                category_key=key,
            )
            await _render_card(
                callback,
                database=database,
                workspace_id=callback_data.workspace_id,
                character_id=callback_data.character_id,
                list_page=0,
                answer="Категория обновлена.",
            )
            return
        if action == "uniset":
            key, requires_story = await _resolve_universe(
                database,
                workspace_id=callback_data.workspace_id,
                item_id=callback_data.item_id,
            )
            await set_workspace_character_universe(
                database,
                workspace_id=callback_data.workspace_id,
                character_id=callback_data.character_id,
                universe_key=key,
            )
            if key is not None and requires_story:
                await _render_taxonomy(
                    callback,
                    database=database,
                    workspace_id=callback_data.workspace_id,
                    character_id=callback_data.character_id,
                    kind="story",
                    page_number=0,
                    list_page=0,
                    answer="Вселенная обновлена. Выберите историю.",
                )
            else:
                await _render_card(
                    callback,
                    database=database,
                    workspace_id=callback_data.workspace_id,
                    character_id=callback_data.character_id,
                    list_page=0,
                    answer="Вселенная обновлена.",
                )
            return
        if action == "storyset":
            assigned = await toggle_workspace_character_story(
                database,
                workspace_id=callback_data.workspace_id,
                character_id=callback_data.character_id,
                story_id=callback_data.item_id,
                assigned_by_user_id=callback.from_user.id,
            )
            await _render_taxonomy(
                callback,
                database=database,
                workspace_id=callback_data.workspace_id,
                character_id=callback_data.character_id,
                kind="story",
                page_number=callback_data.page,
                list_page=0,
                answer="История добавлена." if assigned else "История удалена.",
            )
            return
        await callback.answer("Неизвестное действие.", show_alert=True)
    except (WorkspaceAccessError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)


__all__ = (
    "WorkspaceCharacterPickerCallback",
    "build_character_module_keyboard",
    "router",
)
