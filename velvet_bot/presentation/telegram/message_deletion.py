from __future__ import annotations

from typing import Literal

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

DeleteMessageResult = Literal["deleted", "already_absent"]
_MESSAGE_TO_DELETE_NOT_FOUND = "message to delete not found"


def is_message_already_absent(error: BaseException) -> bool:
    """Return whether Telegram reports that the requested message is already gone."""
    return _MESSAGE_TO_DELETE_NOT_FOUND in str(error).casefold()


async def delete_message_idempotently(
    bot: Bot,
    *,
    chat_id: int,
    message_id: int,
) -> DeleteMessageResult:
    """Delete a Telegram message without treating an already absent message as failure."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest as error:
        if is_message_already_absent(error):
            return "already_absent"
        raise
    return "deleted"


__all__ = (
    "DeleteMessageResult",
    "delete_message_idempotently",
    "is_message_already_absent",
)
