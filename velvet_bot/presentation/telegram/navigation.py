from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TypeVar

from aiogram.types import InlineKeyboardButton

ENTITY_BUTTON_TEXT_LIMIT = 44
TWO_COLUMN_BUTTON_TEXT_LIMIT = 24

_ButtonT = TypeVar("_ButtonT", bound=InlineKeyboardButton)


def compact_button_text(
    value: object,
    *,
    limit: int = ENTITY_BUTTON_TEXT_LIMIT,
    fallback: str = "—",
) -> str:
    """Normalize and safely truncate Telegram button text.

    Telegram accepts long labels, but mobile clients wrap them into tall,
    uneven controls. Entity rows use a wider single-column limit while
    two-column action panels should stay within ``TWO_COLUMN_BUTTON_TEXT_LIMIT``.
    """

    safe_limit = max(4, min(int(limit), 64))
    text = " ".join(str(value or "").split()).strip() or fallback
    if len(text) <= safe_limit:
        return text
    return text[: safe_limit - 1].rstrip() + "…"


def two_column_rows(buttons: Sequence[_ButtonT] | Iterable[_ButtonT]) -> list[list[_ButtonT]]:
    """Arrange buttons into stable two-column rows for desktop and Android."""

    items = list(buttons)
    return [items[index : index + 2] for index in range(0, len(items), 2)]


__all__ = (
    "ENTITY_BUTTON_TEXT_LIMIT",
    "TWO_COLUMN_BUTTON_TEXT_LIMIT",
    "compact_button_text",
    "two_column_rows",
)
