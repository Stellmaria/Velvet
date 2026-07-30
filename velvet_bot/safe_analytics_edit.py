from __future__ import annotations

from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from velvet_bot.presentation.telegram.shared import safe_edit_callback_text


async def safe_analytics_edit(
    callback: CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    await safe_edit_callback_text(
        callback,
        text,
        reply_markup=keyboard,
    )


def install_safe_analytics_edit() -> None:
    """Compatibility no-op: handlers import the safe editor explicitly."""
