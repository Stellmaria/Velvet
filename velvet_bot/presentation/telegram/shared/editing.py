from __future__ import annotations

from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

_MESSAGE_NOT_MODIFIED = "message is not modified"


def is_message_not_modified(error: BaseException) -> bool:
    """Return whether Telegram rejected an edit because the payload is unchanged."""

    return _MESSAGE_NOT_MODIFIED in str(error).casefold()


async def safe_edit_message_text(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    **edit_kwargs: Any,
) -> bool:
    """Edit text and suppress only Telegram's unchanged-message response."""

    try:
        await message.edit_text(text, reply_markup=reply_markup, **edit_kwargs)
    except TelegramBadRequest as error:
        if not is_message_not_modified(error):
            raise
        return False
    return True


async def safe_edit_callback_text(
    callback: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    unavailable_text: str = "Меню больше недоступно.",
    **edit_kwargs: Any,
) -> bool:
    """Edit the message behind a callback while preserving inaccessible-message UX."""

    if not isinstance(callback.message, Message):
        await callback.answer(unavailable_text, show_alert=True)
        return False
    return await safe_edit_message_text(
        callback.message,
        text,
        reply_markup=reply_markup,
        **edit_kwargs,
    )


async def edit_or_answer_callback_text(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    """Edit a callback card or send a replacement when Telegram cannot edit it.

    Media-backed messages are answered with a new text card. Text messages are edited;
    an unchanged payload is ignored, while other Telegram bad requests fall back to a
    new answer. The callback is acknowledged exactly once after presentation handling.
    """

    message = callback.message
    if isinstance(message, Message):
        if message.photo or message.video or message.document:
            await message.answer(text, reply_markup=reply_markup)
        else:
            try:
                await message.edit_text(text, reply_markup=reply_markup)
            except TelegramBadRequest as error:
                if not is_message_not_modified(error):
                    await message.answer(text, reply_markup=reply_markup)
    await callback.answer()


__all__ = (
    "edit_or_answer_callback_text",
    "is_message_not_modified",
    "safe_edit_callback_text",
    "safe_edit_message_text",
)
