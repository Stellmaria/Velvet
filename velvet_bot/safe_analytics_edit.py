from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


async def safe_analytics_edit(
    callback: CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


def install_safe_analytics_edit() -> None:
    """Compatibility no-op: handlers import the safe editor explicitly."""
