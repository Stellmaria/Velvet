from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.archive_ui import ArchiveMediaCallback
from velvet_bot.character_directory import (
    CATEGORY_EMOJI,
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    UNIVERSE_EMOJI,
    UNIVERSE_LABELS,
    UNIVERSE_ORDER,
    CharacterDirectoryItem,
    CharacterDirectoryPage,
    category_label,
    get_character_directory_item,
    list_category_summaries,
    list_character_directory,
    list_universe_summaries,
    normalize_category,
    normalize_universe_category,
    set_character_category,
    set_character_universe_category,
    universe_label,
)
from velvet_bot.database import Database

router = Router(name=__name__)
_WORLD_PREFIX = "world."


class AdminDirectoryCallback(CallbackData, prefix="adir"):
    action: str
    category: str = ""
    page: int = 0
    character_id: int = 0


def _cb(
    action: str,
    *,
    category: str = "",
    page: int = 0,
    character_id: int = 0,
) -> str:
    return AdminDirectoryCallback(
        action=action,
        category=category,
        page=page,
        character_id=character_id,
    ).pack()


def _world_scope(universe_category: str) -> str:
    return f"{_WORLD_PREFIX}{universe_category}"


def _decode_scope(scope: str) -> tuple[str, str]:
    if scope.startswith(_WORLD_PREFIX):
        return "", scope.removeprefix(_WORLD_PREFIX)
    return scope, ""


def _directory_text(total: int) -> str:
    return (
        "<b>Управление архивом персонажей</b>\n\n"
        "У персонажа теперь две независимые категории:\n"
        "• тип: Женский, Мужской, МЖ, ММ или ЖЖ;\n"
        "• вселенная: SHS, КР, ЛМ, Лагерта или Original.\n\n"
        "Обе категории назначаются кнопками в карточке персонажа.\n\n"
        f"Всего персонажей: <b>{total}</b>"
    )


def _directory_keyboard(
    category_summaries,
    universe_summaries,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    category_buttons = [
        InlineKeyboardButton(
            text=f"{item.emoji} {item.label} · {item.character_count}",
            callback_data=_cb("menu", category=item.key),
        )
        for item in category_summaries
    ]
    rows.extend(
        category_buttons[index : index + 2]
        for index in range(0, len(category_buttons), 2)
    )

    universe_buttons = [
        InlineKeyboardButton(
            text=f"{item.emoji} {item.label} · {item.character_count}",
            callback_data=_cb("menu", category=_world_scope(item.key)),
        )
        for item in universe_summaries
    ]
    rows.extend(
        universe_buttons[index : index + 2]
        for index in range(0, len(universe_buttons), 2)
    )

    rows.append(
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data=_cb("categories")),
            InlineKeyboardButton(text="✖ Закрыть", callback_data=_cb("close")),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _page_text(page: CharacterDirectoryPage) -> str:
    if page.universe_category:
        label = UNIVERSE_LABELS.get(page.universe_category, page.universe_category)
        emoji = UNIVERSE_EMOJI.get(page.universe_category, "🌐")
        heading = f"Вселенная: {label}"
    else:
        label = CATEGORY_LABELS.get(page.category, page.category or "Все")
        emoji = CATEGORY_EMOJI.get(page.category, "🗂")
        heading = f"Тип: {label}"
    return (
        f"<b>{emoji} {escape(heading)}</b>\n\n"
        "Сортировка: <b>по алфавиту</b>\n"
        f"Персонажей: <b>{page.total_characters}</b>\n"
        f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>"
    )


def _page_keyboard(
    page: CharacterDirectoryPage,
    *,
    scope: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in page.items:
        row = [
            InlineKeyboardButton(
                text=f"👤 {item.character.name} · {item.media_count}",
                callback_data=_cb(
                    "profile",
                    category=scope,
                    page=page.page,
                    character_id=item.character.id,
                ),
            )
        ]
        if page.universe_category == "uncategorized":
            row.append(
                InlineKeyboardButton(
                    text="🌐 Вселенная",
                    callback_data=_cb(
                        "pickworld",
                        category=scope,
                        page=page.page,
                        character_id=item.character.id,
                    ),
                )
            )
        rows.append(row)

    if page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_cb(
                        "menu",
                        category=scope,
                        page=(page.page - 1) % page.total_pages,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1} / {page.total_pages}",
                    callback_data=_cb("noop"),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_cb(
                        "menu",
                        category=scope,
                        page=(page.page + 1) % page.total_pages,
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="↩️ Все разделы", callback_data=_cb("categories")),
            InlineKeyboardButton(text="✖ Закрыть", callback_data=_cb("close")),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _profile_text(item: CharacterDirectoryItem) -> str:
    return (
        "<b>Карточка персонажа</b>\n\n"
        f"Имя: <b>{escape(item.character.name)}</b>\n"
        f"Тип: <b>{escape(category_label(item.category))}</b>\n"
        f"Вселенная: <b>{escape(universe_label(item.universe_category))}</b>\n"
        f"Материалов: <b>{item.media_count}</b>\n\n"
        "Промты назначаются отдельно каждой картинке или видео внутри архива."
    )


def _profile_keyboard(
    item: CharacterDirectoryItem,
    *,
    scope: str,
    page: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if item.media_count:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🖼 Открыть архив · {item.media_count}",
                    callback_data=ArchiveMediaCallback(
                        action="open",
                        character_id=item.character.id,
                        offset=0,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🏷 Изменить тип",
                callback_data=_cb(
                    "picktype",
                    category=scope,
                    page=page,
                    character_id=item.character.id,
                ),
            ),
            InlineKeyboardButton(
                text="🌐 Выбрать вселенную",
                callback_data=_cb(
                    "pickworld",
                    category=scope,
                    page=page,
                    character_id=item.character.id,
                ),
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К списку",
                callback_data=_cb("menu", category=scope, page=page),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _picker_text(item: CharacterDirectoryItem, *, dimension: str) -> str:
    current = (
        category_label(item.category)
        if dimension == "type"
        else universe_label(item.universe_category)
    )
    title = "тип" if dimension == "type" else "вселенную"
    return (
        f"<b>Выбрать {title}</b>\n\n"
        f"Персонаж: <b>{escape(item.character.name)}</b>\n"
        f"Сейчас: <b>{escape(current)}</b>"
    )


def _type_picker(
    item: CharacterDirectoryItem,
    *,
    scope: str,
    page: int,
) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{CATEGORY_EMOJI[key]} {CATEGORY_LABELS[key]}",
            callback_data=_cb(
                f"settype_{key}",
                category=scope,
                page=page,
                character_id=item.character.id,
            ),
        )
        for key in CATEGORY_ORDER
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(
                text="📦 Без категории",
                callback_data=_cb(
                    "settype_none",
                    category=scope,
                    page=page,
                    character_id=item.character.id,
                ),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Назад",
                callback_data=_cb(
                    "profile",
                    category=scope,
                    page=page,
                    character_id=item.character.id,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _universe_picker(
    item: CharacterDirectoryItem,
    *,
    scope: str,
    page: int,
) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{UNIVERSE_EMOJI[key]} {UNIVERSE_LABELS[key]}",
            callback_data=_cb(
                f"setworld_{key}",
                category=scope,
                page=page,
                character_id=item.character.id,
            ),
        )
        for key in UNIVERSE_ORDER
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(
                text="📭 Без вселенной",
                callback_data=_cb(
                    "setworld_none",
                    category=scope,
                    page=page,
                    character_id=item.character.id,
                ),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Назад",
                callback_data=_cb(
                    "profile",
                    category=scope,
                    page=page,
                    character_id=item.character.id,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _load_directory_summaries(database: Database):
    categories = await list_category_summaries(
        database,
        public_only=False,
        include_uncategorized=True,
    )
    universes = await list_universe_summaries(
        database,
        public_only=False,
        include_uncategorized=True,
    )
    return categories, universes


async def _render_categories(message: Message, database: Database) -> None:
    categories, universes = await _load_directory_summaries(database)
    await message.answer(
        _directory_text(sum(item.character_count for item in categories)),
        reply_markup=_directory_keyboard(categories, universes),
    )


@router.message(Command("characters"))
async def handle_admin_characters(message: Message, database: Database) -> None:
    await _render_categories(message, database)


@router.message(Command("category", "cat"))
async def handle_set_category(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args or len(command.args.rsplit(maxsplit=1)) != 2:
        await message.answer(
            "Формат: <code>/category Имя категория</code>\n"
            "Категории: женский, мужской, мж, мм, жж.\n"
            "Снять категорию: <code>/category Имя без</code>"
        )
        return
    character_name, raw_category = command.args.rsplit(maxsplit=1)
    character = await database.get_character(character_name)
    if character is None:
        await message.answer("Такой персонаж не найден.")
        return
    try:
        category = normalize_category(raw_category, allow_uncategorized=True)
        stored_category = None if category == "uncategorized" else category
        await set_character_category(
            database,
            character_id=character.id,
            category=stored_category,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(
        f"Тип персонажа <b>{escape(character.name)}</b>: "
        f"<b>{escape(category_label(stored_category))}</b>."
    )


@router.message(Command("universe", "world", "source"))
async def handle_set_universe(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args or len(command.args.rsplit(maxsplit=1)) != 2:
        await message.answer(
            "Формат: <code>/universe Имя КР</code>\n"
            "Вселенные: SHS, КР, ЛМ, Лагерта, Original.\n"
            "Снять привязку: <code>/universe Имя без</code>"
        )
        return
    character_name, raw_universe = command.args.rsplit(maxsplit=1)
    character = await database.get_character(character_name)
    if character is None:
        await message.answer("Такой персонаж не найден.")
        return
    try:
        universe = normalize_universe_category(
            raw_universe,
            allow_uncategorized=True,
        )
        stored_universe = None if universe == "uncategorized" else universe
        await set_character_universe_category(
            database,
            character_id=character.id,
            universe_category=stored_universe,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(
        f"Вселенная персонажа <b>{escape(character.name)}</b>: "
        f"<b>{escape(universe_label(stored_universe))}</b>."
    )


async def _show_profile(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    await callback.message.edit_text(
        _profile_text(item),
        reply_markup=_profile_keyboard(
            item,
            scope=callback_data.category,
            page=callback_data.page,
        ),
    )
    await callback.answer()


@router.callback_query(AdminDirectoryCallback.filter())
async def handle_admin_directory_callback(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
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
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return

    if callback_data.action == "categories":
        categories, universes = await _load_directory_summaries(database)
        await callback.message.edit_text(
            _directory_text(sum(item.character_count for item in categories)),
            reply_markup=_directory_keyboard(categories, universes),
        )
        await callback.answer()
        return

    if callback_data.action == "menu":
        category, universe = _decode_scope(callback_data.category)
        page = await list_character_directory(
            database,
            category=category,
            universe_category=universe,
            page=callback_data.page,
            public_only=False,
        )
        await callback.message.edit_text(
            _page_text(page),
            reply_markup=_page_keyboard(page, scope=callback_data.category),
        )
        await callback.answer()
        return

    if callback_data.action == "profile":
        await _show_profile(callback, callback_data, database)
        return

    if callback_data.action in {"picktype", "pickworld"}:
        item = await get_character_directory_item(database, callback_data.character_id)
        if item is None:
            await callback.answer("Персонаж больше не найден.", show_alert=True)
            return
        dimension = "type" if callback_data.action == "picktype" else "world"
        keyboard = (
            _type_picker(item, scope=callback_data.category, page=callback_data.page)
            if dimension == "type"
            else _universe_picker(
                item,
                scope=callback_data.category,
                page=callback_data.page,
            )
        )
        await callback.message.edit_text(
            _picker_text(item, dimension=dimension),
            reply_markup=keyboard,
        )
        await callback.answer()
        return

    if callback_data.action.startswith("settype_"):
        raw_value = callback_data.action.removeprefix("settype_")
        category = None if raw_value == "none" else raw_value
        if category is not None and category not in CATEGORY_ORDER:
            await callback.answer("Неизвестный тип.", show_alert=True)
            return
        await set_character_category(
            database,
            character_id=callback_data.character_id,
            category=category,
        )
        await _show_profile(callback, callback_data, database)
        return

    if callback_data.action.startswith("setworld_"):
        raw_value = callback_data.action.removeprefix("setworld_")
        universe = None if raw_value == "none" else raw_value
        if universe is not None and universe not in UNIVERSE_ORDER:
            await callback.answer("Неизвестная вселенная.", show_alert=True)
            return
        await set_character_universe_category(
            database,
            character_id=callback_data.character_id,
            universe_category=universe,
        )
        await _show_profile(callback, callback_data, database)
        return

    await callback.answer("Неизвестное действие.", show_alert=True)
