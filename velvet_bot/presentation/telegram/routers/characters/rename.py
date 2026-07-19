from __future__ import annotations

import re
from html import escape

from aiogram import F, Router
from aiogram.filters import BaseFilter
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.character_directory import (
    get_character_directory_item,
    list_category_summaries,
)
from velvet_bot.character_renaming import rename_character
from velvet_bot.database import Database
from velvet_bot.domains.characters.catalog import normalize_category
from velvet_bot.presentation.telegram.routers.characters.directory import (
    AdminDirectoryCallback,
    _category_keyboard,
    _category_text,
    _profile_keyboard,
    _profile_text,
)
from velvet_bot.presentation.telegram.routers.characters.navigation import (
    resolve_directory_category,
)

router = Router(name=__name__)

_RENAME_MARKER_RE = re.compile(
    r"^RENAME_CHARACTER:(?P<character_id>\d+):(?P<category>[a-z0-9_-]*):(?P<page>\d+)"
)


class InvalidDirectoryCategoryFilter(BaseFilter):
    async def __call__(
        self,
        callback: CallbackQuery,
        callback_data: AdminDirectoryCallback,
    ) -> bool:
        del callback
        try:
            normalize_category(
                callback_data.category,
                allow_uncategorized=True,
            )
        except ValueError:
            return True
        return False


def _keyboard_with_rename(item, *, category: str, page: int) -> InlineKeyboardMarkup:
    directory_category = resolve_directory_category(category, item.category)
    base = _profile_keyboard(item, category=directory_category, page=page)
    rows = [list(row) for row in base.inline_keyboard]
    if rows:
        rows.pop()
    rows.append(
        [
            InlineKeyboardButton(
                text="✏️ Переименовать",
                callback_data=AdminDirectoryCallback(
                    action="rename",
                    category=directory_category,
                    page=page,
                    character_id=item.character.id,
                ).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К списку",
                callback_data=AdminDirectoryCallback(
                    action="menu",
                    category=directory_category,
                    page=page,
                    character_id=item.character.id,
                ).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def handle_invalid_directory_menu(
    callback: CallbackQuery,
    callback_data: AdminDirectoryCallback,
    database: Database,
) -> None:
    del callback_data
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return

    summaries = await list_category_summaries(
        database,
        public_only=False,
        include_uncategorized=True,
    )
    await callback.message.edit_text(
        _category_text(sum(item.character_count for item in summaries)),
        reply_markup=_category_keyboard(summaries),
    )
    await callback.answer(
        "Категория в старой карточке устарела. Открыт список категорий.",
        show_alert=True,
    )


async def handle_profile_with_rename(
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
    await callback.message.edit_text(
        _profile_text(item),
        reply_markup=_keyboard_with_rename(
            item,
            category=callback_data.category,
            page=callback_data.page,
        ),
    )
    await callback.answer()


async def handle_rename_request(
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
    directory_category = resolve_directory_category(
        callback_data.category,
        item.category,
    )
    marker = (
        f"RENAME_CHARACTER:{item.character.id}:"
        f"{directory_category}:{callback_data.page}"
    )
    await callback.message.answer(
        f"{marker}\n\n"
        f"<b>Переименовать персонажа</b>\n"
        f"Текущее имя: <b>{escape(item.character.name)}</b>\n\n"
        "Ответьте на это сообщение новым именем.",
        reply_markup=ForceReply(
            selective=True,
            input_field_placeholder="Новое имя персонажа",
        ),
    )
    await callback.answer()


@router.message(F.reply_to_message.text.regexp(r"^RENAME_CHARACTER:"))
async def handle_rename_reply(message: Message, database: Database) -> None:
    source = message.reply_to_message.text if message.reply_to_message else ""
    match = _RENAME_MARKER_RE.match(source or "")
    if match is None:
        return
    new_name = (message.text or "").strip()
    if not new_name:
        await message.answer("Новое имя не может быть пустым.")
        return
    character_id = int(match.group("character_id"))
    category = match.group("category")
    page = int(match.group("page"))
    try:
        character = await rename_character(
            database,
            character_id=character_id,
            new_name=new_name,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    item = await get_character_directory_item(database, character.id)
    if item is None:
        await message.answer("Имя изменено, но карточка больше не найдена.")
        return
    await message.answer(
        f"✅ Персонаж переименован в <b>{escape(character.name)}</b>.\n\n"
        f"{_profile_text(item)}",
        reply_markup=_keyboard_with_rename(
            item,
            category=resolve_directory_category(category, item.category),
            page=page,
        ),
    )


router.callback_query.register(
    handle_invalid_directory_menu,
    AdminDirectoryCallback.filter(F.action == "menu"),
    InvalidDirectoryCategoryFilter(),
)
router.callback_query.register(
    handle_profile_with_rename,
    AdminDirectoryCallback.filter(F.action == "profile"),
)
router.callback_query.register(
    handle_rename_request,
    AdminDirectoryCallback.filter(F.action == "rename"),
)

__all__ = ("InvalidDirectoryCategoryFilter", "router")
