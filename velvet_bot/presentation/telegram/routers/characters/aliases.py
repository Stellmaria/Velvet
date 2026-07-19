from __future__ import annotations

import re
from html import escape

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.alias_management import (
    delete_character_alias_by_id,
    get_character_alias_summary,
)
from velvet_bot.application.owner_profiles import (
    add_alias_from_text,
    delete_alias_from_text,
    list_aliases_from_text,
    rebuild_alias_index,
)
from velvet_bot.character_aliases import add_character_alias
from velvet_bot.database import Database

router = Router(name=__name__)

CHARACTER_TAG_REPLY_MARKER = "CHARACTER_TAG:"
_TAG_REPLY_RE = re.compile(r"CHARACTER_TAG:(\d+)")


class CharacterTagCallback(CallbackData, prefix="ctag"):
    action: str
    character_id: int
    alias_id: int = 0
    category: str = ""
    page: int = 0


class CharacterTagReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        reply = message.reply_to_message
        if reply is None:
            return False
        source = reply.text or reply.caption or ""
        return _TAG_REPLY_RE.search(source) is not None


def _tag_callback(
    action: str,
    *,
    character_id: int,
    alias_id: int = 0,
    category: str = "",
    page: int = 0,
) -> str:
    return CharacterTagCallback(
        action=action,
        character_id=character_id,
        alias_id=alias_id,
        category=category,
        page=page,
    ).pack()


def _profile_callback(*, character_id: int, category: str, page: int) -> str:
    from velvet_bot.presentation.telegram.routers.characters.directory import (
        AdminDirectoryCallback,
    )

    return AdminDirectoryCallback(
        action="profile",
        category=category,
        page=page,
        character_id=character_id,
    ).pack()


def _tag_menu(
    *,
    character_id: int,
    category: str,
    page: int,
    items,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        if item.source == "name":
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 Удалить {item.alias[:32]}",
                    callback_data=_tag_callback(
                        "del",
                        character_id=character_id,
                        alias_id=item.id,
                        category=category,
                        page=page,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="➕ Добавить быстрый тег",
                callback_data=_tag_callback(
                    "add",
                    character_id=character_id,
                    category=category,
                    page=page,
                ),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К карточке",
                callback_data=_profile_callback(
                    character_id=character_id,
                    category=category,
                    page=page,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_tag_menu(
    callback: CallbackQuery,
    database: Database,
    callback_data: CharacterTagCallback,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    name, items = await get_character_alias_summary(
        database,
        character_id=callback_data.character_id,
    )
    if name is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    manual = [item for item in items if item.source != "name"]
    lines = [f"• <code>{escape(item.alias)}</code>" for item in manual]
    text = (
        f"<b>🏷 Быстрые теги: {escape(name)}</b>\n\n"
        + ("\n".join(lines) if lines else "• быстрых тегов пока нет")
        + "\n\nТег можно использовать вместо полного имени: "
        "<code>/save Тег</code>, <code>/refs Тег</code>, "
        "<code>/character Тег</code>."
    )
    await callback.message.edit_text(
        text,
        reply_markup=_tag_menu(
            character_id=callback_data.character_id,
            category=callback_data.category,
            page=callback_data.page,
            items=items,
        ),
    )


@router.message(Command("aliasadd", "tagadd"))
async def handle_alias_add(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer(
            "Формат: <code>/tagadd ИмяПерсонажа Тег</code>\n"
            "Пример: <code>/tagadd Макс Кроу Кроу</code>"
        )
        return
    try:
        item = await add_alias_from_text(
            database,
            command.args,
            actor_id=message.from_user.id if message.from_user else None,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(
        f"Быстрый тег <code>{escape(item.alias)}</code> назначен персонажу "
        f"<b>{escape(item.character_name)}</b>. Теперь его можно использовать в "
        "<code>/save</code> и командах референсов."
    )


@router.message(Command("aliases", "tags"))
async def handle_alias_list(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer("Формат: <code>/tags ИмяПерсонажа</code>")
        return
    try:
        character, items = await list_aliases_from_text(database, command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    lines = [
        f"• <code>{escape(item.alias)}</code>"
        + (" · основное имя" if item.source == "name" else "")
        for item in items
    ] or ["• тегов пока нет"]
    await message.answer(
        f"<b>Теги: {escape(character.name)}</b>\n\n" + "\n".join(lines)
    )


@router.message(Command("aliasdel", "tagdel"))
async def handle_alias_delete(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer("Формат: <code>/tagdel ИмяПерсонажа Тег</code>")
        return
    try:
        result = await delete_alias_from_text(database, command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    if not result.deleted:
        await message.answer(
            "Тег не найден или это основное имя персонажа, которое удалять нельзя."
        )
        return
    await message.answer(
        f"Быстрый тег <code>{escape(result.alias)}</code> удалён у "
        f"<b>{escape(result.character.name)}</b>."
    )


@router.message(Command("aliasreindex", "tagreindex"))
async def handle_alias_reindex(message: Message, database: Database) -> None:
    result = await rebuild_alias_index(database)
    await message.answer(
        "<b>Индекс тегов пересобран.</b>\n\n"
        f"Новых тегов основного имени: <b>{result.created_name_aliases}</b>\n"
        f"Распознано связей: <b>{result.matched_links}</b> из "
        f"<b>{result.total_hashtags}</b>."
    )


async def handle_character_tag_callback(
    callback: CallbackQuery,
    callback_data: CharacterTagCallback,
    database: Database,
) -> None:
    if callback_data.action == "menu":
        await _render_tag_menu(callback, database, callback_data)
        await callback.answer()
        return
    if callback_data.action == "add":
        if not isinstance(callback.message, Message):
            await callback.answer("Меню больше недоступно.", show_alert=True)
            return
        name, _ = await get_character_alias_summary(
            database,
            character_id=callback_data.character_id,
        )
        if name is None:
            await callback.answer("Персонаж больше не найден.", show_alert=True)
            return
        await callback.message.answer(
            f"<b>Новый быстрый тег: {escape(name)}</b>\n\n"
            "Ответьте на это сообщение коротким именем.\n"
            "Пример: <code>Кроу</code>\n\n"
            f"<code>{CHARACTER_TAG_REPLY_MARKER}{callback_data.character_id}</code>",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="Кроу",
            ),
        )
        await callback.answer("Пришлите тег ответом на сообщение.")
        return
    if callback_data.action == "del":
        name, items = await get_character_alias_summary(
            database,
            character_id=callback_data.character_id,
        )
        item = next(
            (value for value in items if value.id == callback_data.alias_id),
            None,
        )
        if name is None or item is None or item.source == "name":
            await callback.answer("Этот тег нельзя удалить.", show_alert=True)
            return
        if not isinstance(callback.message, Message):
            await callback.answer("Меню больше недоступно.", show_alert=True)
            return
        await callback.message.edit_text(
            f"Удалить быстрый тег <code>{escape(item.alias)}</code> у "
            f"<b>{escape(name)}</b>?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🗑 Да, удалить",
                            callback_data=_tag_callback(
                                "delok",
                                character_id=callback_data.character_id,
                                alias_id=item.id,
                                category=callback_data.category,
                                page=callback_data.page,
                            ),
                        ),
                        InlineKeyboardButton(
                            text="Отмена",
                            callback_data=_tag_callback(
                                "menu",
                                character_id=callback_data.character_id,
                                category=callback_data.category,
                                page=callback_data.page,
                            ),
                        ),
                    ]
                ]
            ),
        )
        await callback.answer()
        return
    if callback_data.action == "delok":
        deleted = await delete_character_alias_by_id(
            database,
            alias_id=callback_data.alias_id,
        )
        if deleted is None:
            await callback.answer("Тег уже удалён или защищён.", show_alert=True)
            return
        await _render_tag_menu(callback, database, callback_data)
        await callback.answer(f"Тег {deleted.alias} удалён.", show_alert=True)
        return
    await callback.answer("Неизвестное действие.", show_alert=True)


@router.message(CharacterTagReplyFilter())
async def handle_character_tag_reply(
    message: Message,
    database: Database,
) -> None:
    reply = message.reply_to_message
    marker_source = (reply.text or reply.caption or "") if reply else ""
    match = _TAG_REPLY_RE.search(marker_source)
    if match is None:
        return
    tag = (message.text or message.caption or "").strip().lstrip("#")
    if not tag:
        await message.answer("Пришлите текст тега, например <code>Кроу</code>.")
        return
    try:
        item = await add_character_alias(
            database,
            character_id=int(match.group(1)),
            alias=tag,
            created_by=message.from_user.id if message.from_user else None,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(
        f"Быстрый тег <code>{escape(item.alias)}</code> добавлен персонажу "
        f"<b>{escape(item.character_name)}</b>.\n\n"
        f"Теперь можно писать <code>/save {escape(item.alias)}</code> или "
        f"<code>/refs {escape(item.alias)}</code>.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏷 Открыть теги",
                        callback_data=_tag_callback(
                            "menu",
                            character_id=item.character_id,
                        ),
                    )
                ]
            ]
        ),
    )


router.callback_query.register(
    handle_character_tag_callback,
    CharacterTagCallback.filter(),
)

__all__ = (
    "CHARACTER_TAG_REPLY_MARKER",
    "CharacterTagCallback",
    "router",
)
