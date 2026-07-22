from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class GuidedWorkspaceCallback(CallbackData, prefix="wqa"):
    action: str
    workspace_id: int
    character_id: int = 0
    item_id: int = 0
    page: int = 0


def guided_workspace_callback(
    action: str,
    *,
    workspace_id: int,
    character_id: int = 0,
    item_id: int = 0,
    page: int = 0,
) -> str:
    return GuidedWorkspaceCallback(
        action=action,
        workspace_id=int(workspace_id),
        character_id=int(character_id),
        item_id=int(item_id),
        page=max(0, int(page)),
    ).pack()


def build_prompt_back_keyboard(
    *,
    workspace_id: int,
    action: str,
    character_id: int = 0,
    text: str = "↩️ Назад",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=guided_workspace_callback(
                        action,
                        workspace_id=workspace_id,
                        character_id=character_id,
                    ),
                )
            ]
        ]
    )


__all__ = (
    "GuidedWorkspaceCallback",
    "build_prompt_back_keyboard",
    "guided_workspace_callback",
)
