from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

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
    list_character_directory,
    set_character_category,
    set_character_universe,
    universe_label,
)
from velvet_bot.database import Database
from velvet_bot.presentation.telegram.navigation import compact_button_text
from velvet_bot.presentation.telegram.routers.characters.contracts import (
    AdminDirectoryCallback,
)
from velvet_bot.presentation.telegram.routers.characters.profile_views import (
    build_character_profile_keyboard,
    format_character_profile,
)

router = Router(name=__name__)


def _cb(
    action: str,
    *,
    category: str = "",
    universe: str = "",
    page: int = 0,
    character_id: int = 0,
    return_category: str = "",
) -> str:
    return AdminDirectoryCallback(
        action=action,
        category=category,
        universe=universe,
        page=page,
        character_id=character_id,
        return_category=return_category,
    ).pack()


def _page_text(page: CharacterDirectoryPage) -> str:
    return (
        "<b>📦 Без категории</b>\n\n"
        "Назначьте персонажу пол/состав, затем вселенную. После назначения "
        "пола карточка исчезнет из этого раздела.\n\n"
        "Сортировка: <b>по алфавиту</b>\n"
        f"Персонажей: <b>{page.total_characters}</b>\n"
        f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>"
    )


def build_uncategorized_keyboard(page: CharacterDirectoryPage) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in page.items:
        row = [
            InlineKeyboardButton(
                text=compact_button_text(f"👤 {item.character.name} · {item.media_count}"),
                callback_data=_cb(
                    "profile",
                    category="uncategorized",
                    page=page.page,
                    character_id=item.character.id,
                ),
            ),
            InlineKeyboardButton(
                text="👥 Пол / состав",
                callback_data=_cb(
                    "pickcat",
                    category="uncategorized",
                    page=page.page,
                    character_id=item.character.id,
                ),
            ),
        ]
        rows.append(row)

    if page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_cb(
                        "menu",
                        category="uncategorized",
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
                        category="uncategorized",
                        page=(page.page + 1) % page.total_pages,
                    ),
                ),
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Категории",
                callback_data=_cb("categories"),
            ),
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=_cb(
                    "menu",
                    category="uncategorized",
                    page=page.page,
                ),
            ),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="✖ Закрыть", callback_data=_cb("close"))]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _category_picker_text(item: CharacterDirectoryItem) -> str:
    return (
        "<b>Назначить пол / состав</b>\n\n"
        f"Персонаж: <b>{escape(item.character.name)}</b>\n"
        f"Текущее значение: <b>{escape(category_label(item.category))}</b>\n\n"
        "После этого выберите вселенную."
    )


def build_category_picker(
    item: CharacterDirectoryItem,
    *,
    page: int,
    return_category: str = "uncategorized",
) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{CATEGORY_EMOJI[category]} {CATEGORY_LABELS[category]}",
            callback_data=_cb(
                "setcat",
                category=category,
                page=page,
                character_id=item.character.id,
                return_category=return_category,
            ),
        )
        for category in CATEGORY_ORDER
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Назад",
                callback_data=_cb(
                    "profile",
                    category=return_category,
                    page=page,
                    character_id=item.character.id,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _universe_picker_text(item: CharacterDirectoryItem) -> str:
    return (
        "<b>Назначить вселенную</b>\n\n"
        f"Персонаж: <b>{escape(item.character.name)}</b>\n"
        f"Пол / состав: <b>{escape(category_label(item.category))}</b>\n"
        f"Текущая вселенная: <b>{escape(universe_label(item.universe))}</b>"
    )


def build_universe_picker(
    item: CharacterDirectoryItem,
    *,
    page: int,
    return_category: str,
) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{UNIVERSE_EMOJI[universe]} {UNIVERSE_LABELS[universe]}",
            callback_data=_cb(
                "setuni",
                universe=universe,
                page=page,
                character_id=item.character.id,
                return_category=return_category,
            ),
        )
        for universe in UNIVERSE_ORDER
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К карточке",
                callback_data=_cb(
                    "profile",
                    category=return_category,
                    page=page,
                    character_id=item.character.id,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_uncategorized_page(
    callback: CallbackQuery,
    database: Database,
    *,
    page_number: int,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return

    page = await list_character_directory(
        database,
        category="uncategorized",
        page=page_number,
        public_only=False,
    )
    try:
        await callback.message.edit_text(
            _page_text(page),
            reply_markup=build_uncategorized_keyboard(page),
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise
    await callback.answer()


async def _render_profile(
    callback: CallbackQuery,
    item: CharacterDirectoryItem,
    *,
    return_category: str,
    page: int,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await callback.message.edit_text(
        format_character_profile(item),
        reply_markup=build_character_profile_keyboard(
            item,
            category=return_category,
            page=page,
        ),
    )


@router.callback_query(
    AdminDirectoryCallback.filter(
        (F.action == "menu") & (F.category == "uncategorized")
    )
)
async def handle_uncategorized_menu(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    await _render_uncategorized_page(
        callback,
        database,
        page_number=callback_data.page,
    )


@router.callback_query(AdminDirectoryCallback.filter(F.action == "pickcat"))
async def handle_category_picker(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return

    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return

    return_category = callback_data.category or "uncategorized"
    await callback.message.edit_text(
        _category_picker_text(item),
        reply_markup=build_category_picker(
            item,
            page=callback_data.page,
            return_category=return_category,
        ),
    )
    await callback.answer()


@router.callback_query(AdminDirectoryCallback.filter(F.action == "setcat"))
async def handle_category_assignment(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    if callback_data.category not in CATEGORY_ORDER:
        await callback.answer("Неизвестная категория.", show_alert=True)
        return

    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return

    await set_character_category(
        database,
        character_id=item.character.id,
        category=callback_data.category,
    )
    item = await get_character_directory_item(database, item.character.id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return

    return_category = callback_data.return_category or callback_data.category
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            _universe_picker_text(item),
            reply_markup=build_universe_picker(
                item,
                page=callback_data.page,
                return_category=return_category,
            ),
        )
    await callback.answer(
        f"{item.character.name}: {CATEGORY_LABELS[callback_data.category]}. "
        "Теперь выберите вселенную.",
        show_alert=True,
    )


@router.callback_query(AdminDirectoryCallback.filter(F.action == "pickuni"))
async def handle_universe_picker(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return

    item = await get_character_directory_item(database, callback_data.character_id)
    if item is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return

    return_category = callback_data.category or item.category or "uncategorized"
    await callback.message.edit_text(
        _universe_picker_text(item),
        reply_markup=build_universe_picker(
            item,
            page=callback_data.page,
            return_category=return_category,
        ),
    )
    await callback.answer()


@router.callback_query(AdminDirectoryCallback.filter(F.action == "setuni"))
async def handle_universe_assignment(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    if callback_data.universe not in UNIVERSE_ORDER:
        await callback.answer("Неизвестная вселенная.", show_alert=True)
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

    return_category = callback_data.return_category or item.category or "uncategorized"
    if return_category == "uncategorized":
        await _render_uncategorized_page(
            callback,
            database,
            page_number=callback_data.page,
        )
        return

    await _render_profile(
        callback,
        item,
        return_category=return_category,
        page=callback_data.page,
    )
    await callback.answer(
        f"{item.character.name}: {UNIVERSE_LABELS[callback_data.universe]}",
        show_alert=True,
    )
