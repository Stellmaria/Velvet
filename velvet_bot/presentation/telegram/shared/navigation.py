from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


@dataclass(frozen=True, slots=True)
class NavigationButton:
    text: str
    callback_data: str


def _button(spec: NavigationButton) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=spec.text, callback_data=spec.callback_data)


def build_navigation_keyboard(
    rows: Sequence[Sequence[NavigationButton]],
) -> InlineKeyboardMarkup:
    """Build an inline keyboard from transport-only button specifications."""

    return InlineKeyboardMarkup(
        inline_keyboard=[[_button(spec) for spec in row] for row in rows]
    )


def build_back_refresh_keyboard(
    *,
    back: NavigationButton,
    refresh_callback_data: str,
    refresh_text: str = "🔄 Обновить",
) -> InlineKeyboardMarkup:
    return build_navigation_keyboard(
        (
            (
                back,
                NavigationButton(
                    text=refresh_text,
                    callback_data=refresh_callback_data,
                ),
            ),
        )
    )


def build_pagination_keyboard(
    *,
    page: int,
    total_pages: int,
    callback_for_page: Callable[[int], str],
    back: NavigationButton | None = None,
    previous_text: str = "⬅️",
    next_text: str = "➡️",
) -> InlineKeyboardMarkup:
    """Build stable one-based pagination without embedding domain decisions."""

    if total_pages < 1:
        raise ValueError("total_pages must be at least 1")
    if page < 1 or page > total_pages:
        raise ValueError("page must be inside the available range")

    pager: list[NavigationButton] = []
    if page > 1:
        pager.append(
            NavigationButton(
                text=previous_text,
                callback_data=callback_for_page(page - 1),
            )
        )
    pager.append(
        NavigationButton(
            text=f"{page}/{total_pages}",
            callback_data=callback_for_page(page),
        )
    )
    if page < total_pages:
        pager.append(
            NavigationButton(
                text=next_text,
                callback_data=callback_for_page(page + 1),
            )
        )

    rows: list[Sequence[NavigationButton]] = [tuple(pager)]
    if back is not None:
        rows.append((back,))
    return build_navigation_keyboard(rows)


__all__ = (
    "NavigationButton",
    "build_back_refresh_keyboard",
    "build_navigation_keyboard",
    "build_pagination_keyboard",
)
