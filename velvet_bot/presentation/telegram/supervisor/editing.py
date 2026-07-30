from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, Message

from velvet_bot.presentation.telegram.shared import safe_edit_message_text


async def edit_supervisor_message(
    message: Message,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    """Edit a Supervisor card through the canonical Telegram editing contract."""

    await safe_edit_message_text(
        message,
        text,
        reply_markup=keyboard,
    )


__all__ = ("edit_supervisor_message",)
