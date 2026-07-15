from __future__ import annotations

from html import escape

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.reference_catalog import ReferencePage


class ReferenceCallback(CallbackData, prefix="ref"):
    action: str
    character_id: int
    offset: int


def build_reference_keyboard(page: ReferencePage) -> InlineKeyboardMarkup:
    if page.total <= 0:
        return InlineKeyboardMarkup(inline_keyboard=[])

    counter = InlineKeyboardButton(
        text=f"{page.offset + 1} / {page.total}",
        callback_data=ReferenceCallback(
            action="noop",
            character_id=page.character.id,
            offset=page.offset,
        ).pack(),
    )
    if page.total == 1:
        rows = [[counter]]
    else:
        rows = [
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=ReferenceCallback(
                        action="show",
                        character_id=page.character.id,
                        offset=(page.offset - 1) % page.total,
                    ).pack(),
                ),
                counter,
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=ReferenceCallback(
                        action="show",
                        character_id=page.character.id,
                        offset=(page.offset + 1) % page.total,
                    ).pack(),
                ),
            ]
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_reference_caption(page: ReferencePage) -> str:
    return (
        f"<b>{escape(page.character.name)}</b> · референс "
        f"<b>{page.offset + 1}</b> из <b>{page.total}</b>"
    )
