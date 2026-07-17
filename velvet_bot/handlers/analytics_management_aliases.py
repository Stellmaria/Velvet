from __future__ import annotations

import re
from html import escape

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
from velvet_bot.analytics_callbacks import AnalyticsManageCallback, management_link
from velvet_bot.character_aliases import add_character_alias
from velvet_bot.database import Database
from velvet_bot.handlers.analytics_management_common import (
    _edit,
    _short,
    _show_character_picker,
)

_ALIAS_REPLY_RE = re.compile(r"ALIAS_CHARACTER:(\d+)")
ALIAS_ACTIONS = frozenset(
    {"aliases", "aliaschar", "aliasadd", "aliasdel", "aliasdelok"}
)

async def _show_character_aliases(
    callback: CallbackQuery,
    database: Database,
    *,
    character_id: int,
    period: str,
    return_page: int,
) -> None:
    name, items = await get_character_alias_summary(
        database,
        character_id=character_id,
    )
    if name is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    lines = []
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        suffix = " · основное имя" if item.source == "name" else ""
        lines.append(f"• <code>#{escape(item.alias)}</code>{suffix}")
        if item.source != "name":
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🗑 Удалить #{_short(item.alias, 30)}",
                        callback_data=management_link(
                            "aliasdel",
                            period=period,
                            character_id=character_id,
                            alias_id=item.id,
                            page=return_page,
                        ),
                    )
                ]
            )
    rows.append(
        [
            InlineKeyboardButton(
                text="➕ Добавить алиас",
                callback_data=management_link(
                    "aliasadd",
                    period=period,
                    character_id=character_id,
                    page=return_page,
                ),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К персонажам",
                callback_data=management_link(
                    "aliases",
                    period=period,
                    page=return_page,
                ),
            )
        ]
    )
    text = (
        f"<b>Алиасы: {escape(name)}</b>\n\n"
        + ("\n".join(lines) if lines else "• алиасов пока нет")
        + "\n\nОсновное имя удалить нельзя. Ручные варианты можно удалить кнопками."
    )
    await _edit(callback, text, InlineKeyboardMarkup(inline_keyboard=rows))

async def handle_alias_action(
    callback: CallbackQuery,
    callback_data: AnalyticsManageCallback,
    database: Database,
    *,
    period: str,
) -> bool:
    action = callback_data.action
    if action not in ALIAS_ACTIONS:
        return False

    if action == "aliases":
        await _show_character_picker(
            callback,
            database,
            action=action,
            period=period,
            page_number=callback_data.page,
        )
    elif action == "aliaschar":
        await _show_character_aliases(
            callback,
            database,
            character_id=callback_data.character_id,
            period=period,
            return_page=callback_data.page,
        )
    elif action == "aliasadd":
        name, _ = await get_character_alias_summary(
            database,
            character_id=callback_data.character_id,
        )
        if name is None or not isinstance(callback.message, Message):
            await callback.answer("Персонаж больше не найден.", show_alert=True)
            return True
        marker = f"ALIAS_CHARACTER:{callback_data.character_id}"
        await callback.message.answer(
            f"<b>Новый алиас: {escape(name)}</b>\n\n"
            "Ответьте на это сообщение новым вариантом хэштега без обязательного символа #.\n"
            "Пример: <code>KaelLang</code>\n\n"
            f"<code>{marker}</code>",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="KaelLang",
            ),
        )
        await callback.answer("Пришлите алиас ответом на сообщение.")
        return True
    elif action == "aliasdel":
        name, items = await get_character_alias_summary(
            database,
            character_id=callback_data.character_id,
        )
        item = next(
            (value for value in items if value.id == callback_data.alias_id),
            None,
        )
        if name is None or item is None or item.source == "name":
            await callback.answer("Алиас нельзя удалить.", show_alert=True)
            return True
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗑 Да, удалить",
                        callback_data=management_link(
                            "aliasdelok",
                            period=period,
                            character_id=callback_data.character_id,
                            alias_id=item.id,
                            page=callback_data.page,
                        ),
                    ),
                    InlineKeyboardButton(
                        text="Отмена",
                        callback_data=management_link(
                            "aliaschar",
                            period=period,
                            character_id=callback_data.character_id,
                            page=callback_data.page,
                        ),
                    ),
                ]
            ]
        )
        await _edit(
            callback,
            f"Удалить алиас <code>#{escape(item.alias)}</code> у "
            f"<b>{escape(name)}</b>?

"
            "Совпадающие старые хэштеги снова станут нераспознанными.",
            keyboard,
        )
    else:
        deleted = await delete_character_alias_by_id(
            database,
            alias_id=callback_data.alias_id,
        )
        if deleted is None:
            await callback.answer("Алиас уже удалён или защищён.", show_alert=True)
            return True
        await _show_character_aliases(
            callback,
            database,
            character_id=deleted.character_id,
            period=period,
            return_page=callback_data.page,
        )
        await callback.answer(f"Алиас #{deleted.alias} удалён.", show_alert=True)
        return True

    await callback.answer()
    return True


async def handle_alias_reply_message(
    message: Message,
    database: Database,
) -> None:
    reply = message.reply_to_message
    if reply is None:
        return
    marker_source = reply.text or reply.caption or ""
    match = _ALIAS_REPLY_RE.search(marker_source)
    if match is None:
        return
    alias_text = (message.text or message.caption or "").strip().lstrip("#")
    if not alias_text:
        await message.answer("Пришлите текст алиаса, например <code>KaelLang</code>.")
        return
    character_id = int(match.group(1))
    try:
        item = await add_character_alias(
            database,
            character_id=character_id,
            alias=alias_text,
            created_by=message.from_user.id if message.from_user else None,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(
        f"Алиас <code>#{escape(item.alias)}</code> добавлен персонажу "
        f"<b>{escape(item.character_name)}</b>. Старые посты пересчитаны.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔤 Открыть алиасы",
                        callback_data=management_link(
                            "aliaschar",
                            character_id=item.character_id,
                        ),
                    )
                ]
            ]
        ),
    )

__all__ = (
    "ALIAS_ACTIONS",
    "handle_alias_action",
    "handle_alias_reply_message",
)
