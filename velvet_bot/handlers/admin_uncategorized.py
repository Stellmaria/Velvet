from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.character_directory import (
    CATEGORY_EMOJI,
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    CharacterDirectoryItem,
    CharacterDirectoryPage,
    get_character_directory_item,
    list_character_directory,
    set_character_category,
)
from velvet_bot.database import Database
from velvet_bot.handlers.admin_directory import AdminDirectoryCallback

router = Router(name=__name__)


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


def _page_text(page: CharacterDirectoryPage) -> str:
    return (
        "<b>📦 Без категории</b>\n\n"
        "Выберите категорию кнопкой возле персонажа. После назначения персонаж "
        "сразу исчезнет из этого раздела и появится в нужной категории.\n\n"
        "Сортировка: <b>по алфавиту</b>\n"
        f"Персонажей: <b>{page.total_characters}</b>\n"
        f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>"
    )


def build_uncategorized_keyboard(page: CharacterDirectoryPage) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in page.items:
        row = [
            InlineKeyboardButton(
                text=f"👤 {item.character.name} · {item.media_count}",
                callback_data=_cb(
                    "profile",
                    category="uncategorized",
                    page=page.page,
                    character_id=item.character.id,
                ),
            ),
            InlineKeyboardButton(
                text="🏷 Категория",
                callback_data=_cb(
                    "pickcat",
                    category="uncategorized",
                    page=page.page,
                    character_id=item.character.id,
                ),
            ),
        ]
        if item.prompt_post_url:
            row.append(InlineKeyboardButton(text="📝", url=item.prompt_post_url))
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


def _picker_text(item: CharacterDirectoryItem) -> str:
    return (
        "<b>Назначить категорию</b>\n\n"
        f"Персонаж: <b>{escape(item.character.name)}</b>\n"
        "Текущая категория: <b>Без категории</b>\n\n"
        "Выберите раздел, в который нужно перенести карточку."
    )


def build_category_picker(
    item: CharacterDirectoryItem,
    *,
    page: int,
) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{CATEGORY_EMOJI[category]} {CATEGORY_LABELS[category]}",
            callback_data=_cb(
                "setcat",
                category=category,
                page=page,
                character_id=item.character.id,
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
                    "menu",
                    category="uncategorized",
                    page=page,
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
    if item.category is not None:
        await callback.answer(
            "Категория уже назначена. Обновите список.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        _picker_text(item),
        reply_markup=build_category_picker(item, page=callback_data.page),
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

    if not isinstance(callback.message, Message):
        await callback.answer(
            f"Категория: {CATEGORY_LABELS[callback_data.category]}",
            show_alert=True,
        )
        return

    page = await list_character_directory(
        database,
        category="uncategorized",
        page=callback_data.page,
        public_only=False,
    )
    await callback.message.edit_text(
        _page_text(page),
        reply_markup=build_uncategorized_keyboard(page),
    )
    await callback.answer(
        f"{item.character.name}: {CATEGORY_LABELS[callback_data.category]}",
        show_alert=True,
    )
