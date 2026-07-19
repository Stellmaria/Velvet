from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class AdminDirectoryCallback(CallbackData, prefix="adir"):
    action: str
    category: str = ""
    universe: str = ""
    page: int = 0
    character_id: int = 0
    return_category: str = ""
    story_id: int = 0


def directory_callback(
    action: str,
    *,
    category: str = "",
    universe: str = "",
    page: int = 0,
    character_id: int = 0,
    return_category: str = "",
    story_id: int = 0,
) -> str:
    return AdminDirectoryCallback(
        action=action,
        category=category,
        universe=universe,
        page=page,
        character_id=character_id,
        return_category=return_category,
        story_id=story_id,
    ).pack()


__all__ = ("AdminDirectoryCallback", "directory_callback")
