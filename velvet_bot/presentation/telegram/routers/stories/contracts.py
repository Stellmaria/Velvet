from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class AdminStoryCallback(CallbackData, prefix="astory"):
    action: str
    category: str = ""
    directory_page: int = 0
    story_page: int = 0
    character_id: int = 0
    story_id: int = 0


def story_callback(
    action: str,
    *,
    category: str,
    directory_page: int,
    story_page: int,
    character_id: int,
    story_id: int = 0,
) -> str:
    return AdminStoryCallback(
        action=action,
        category=category,
        directory_page=directory_page,
        story_page=story_page,
        character_id=character_id,
        story_id=story_id,
    ).pack()


__all__ = ("AdminStoryCallback", "story_callback")
