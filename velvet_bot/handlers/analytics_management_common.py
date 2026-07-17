from __future__ import annotations

from html import escape

from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.analytics_callbacks import dashboard_link, management_link
from velvet_bot.analytics_review import CharacterPickerItem, ReviewPage, list_character_picker
from velvet_bot.character_directory import category_label, universe_label
from velvet_bot.database import Database

def _primary_channel_id(analytics_channel_ids: frozenset[int]) -> int | None:
    return sorted(analytics_channel_ids)[0] if analytics_channel_ids else None

def _short(value: str, limit: int = 42) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(1, limit - 1)].rstrip() + "…"

def _date(value) -> str:
    return value.astimezone().strftime("%d.%m.%Y") if value else "—"

async def _edit(
    callback: CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await callback.message.edit_text(text, reply_markup=keyboard)

def _pager(
    *,
    action: str,
    period: str,
    page: ReviewPage,
    token_id: int = 0,
    character_id: int = 0,
    value: str = "",
) -> list[InlineKeyboardButton]:
    if page.total_pages <= 1:
        return []
    return [
        InlineKeyboardButton(
            text="◀️",
            callback_data=management_link(
                action,
                period=period,
                page=(page.page - 1) % page.total_pages,
                token_id=token_id,
                character_id=character_id,
                value=value,
            ),
        ),
        InlineKeyboardButton(
            text=f"{page.page + 1} / {page.total_pages}",
            callback_data=management_link("noop"),
        ),
        InlineKeyboardButton(
            text="▶️",
            callback_data=management_link(
                action,
                period=period,
                page=(page.page + 1) % page.total_pages,
                token_id=token_id,
                character_id=character_id,
                value=value,
            ),
        ),
    ]

def _character_detail(item: CharacterPickerItem) -> str:
    details = [category_label(item.category), universe_label(item.universe)]
    if item.story_short_label:
        details.append(item.story_short_label)
    return " / ".join(value for value in details if value)

async def _show_character_picker(
    callback: CallbackQuery,
    database: Database,
    *,
    action: str,
    period: str,
    page_number: int,
    token_id: int = 0,
) -> None:
    page = await list_character_picker(database, page=page_number)
    rows: list[list[InlineKeyboardButton]] = []
    for raw_item in page.items:
        item = raw_item
        if not isinstance(item, CharacterPickerItem):
            continue
        target_action = "tagassign" if action == "tagchars" else "aliaschar"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{_short(item.name, 30)} · {_short(_character_detail(item), 22)}",
                    callback_data=management_link(
                        target_action,
                        period=period,
                        token_id=token_id,
                        character_id=item.id,
                        page=page.page,
                    ),
                )
            ]
        )
    pager = _pager(
        action=action,
        period=period,
        page=page,
        token_id=token_id,
    )
    if pager:
        rows.append(pager)
    back_data = (
        management_link("tag", period=period, token_id=token_id)
        if action == "tagchars"
        else dashboard_link("menu", period=period)
    )
    rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=back_data)])
    title = "Назначить хэштег персонажу" if action == "tagchars" else "Алиасы персонажей"
    text = (
        f"<b>{title}</b>\n\n"
        f"Персонажей: <b>{page.total_items}</b>\n"
        "Выберите персонажа из списка."
    )
    await _edit(callback, text, InlineKeyboardMarkup(inline_keyboard=rows))

__all__ = (
    "_character_detail",
    "_date",
    "_edit",
    "_pager",
    "_primary_channel_id",
    "_short",
    "_show_character_picker",
)
