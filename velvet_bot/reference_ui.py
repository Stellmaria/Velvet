from __future__ import annotations

from html import escape

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.reference_catalog import ReferencePage


class ReferenceCallback(CallbackData, prefix="ref"):
    action: str
    character_id: int
    reference_id: int
    offset: int


def _callback(page: ReferencePage, action: str, offset: int | None = None) -> str:
    if page.reference is None:
        raise ValueError("Нельзя построить кнопку без референса.")
    return ReferenceCallback(
        action=action,
        character_id=page.character.id,
        reference_id=page.reference.id,
        offset=page.offset if offset is None else offset,
    ).pack()


def build_reference_keyboard(page: ReferencePage) -> InlineKeyboardMarkup:
    if page.total <= 0 or page.reference is None:
        return InlineKeyboardMarkup(inline_keyboard=[])

    counter = InlineKeyboardButton(
        text=f"{page.offset + 1} / {page.total}",
        callback_data=_callback(page, "noop"),
    )
    if page.total == 1:
        rows = [[counter]]
    else:
        rows = [
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_callback(
                        page,
                        "show",
                        (page.offset - 1) % page.total,
                    ),
                ),
                counter,
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_callback(
                        page,
                        "show",
                        (page.offset + 1) % page.total,
                    ),
                ),
            ]
        ]

    rows.append(
        [
            InlineKeyboardButton(
                text="🗑 Удалить референс",
                callback_data=_callback(page, "delete_prompt"),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔎 Сравнить результат",
                callback_data=_callback(page, "compare_help"),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_reference_delete_keyboard(page: ReferencePage) -> InlineKeyboardMarkup:
    if page.reference is None:
        return InlineKeyboardMarkup(inline_keyboard=[])
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить",
                    callback_data=_callback(page, "delete"),
                ),
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data=_callback(page, "cancel_delete"),
                ),
            ]
        ]
    )


def format_reference_caption(page: ReferencePage) -> str:
    return (
        f"<b>{escape(page.character.name)}</b> · референс "
        f"<b>{page.offset + 1}</b> из <b>{page.total}</b>"
    )
