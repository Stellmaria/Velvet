from __future__ import annotations

from typing import Literal

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

DeleteMessageResult = Literal["deleted", "already_absent", "not_deletable"]
_MESSAGE_TO_DELETE_NOT_FOUND = "message to delete not found"
_MESSAGE_NOT_DELETABLE_MARKERS = (
    "message can't be deleted",
    "message cannot be deleted",
)


def is_message_already_absent(error: BaseException) -> bool:
    """Return whether Telegram reports that the requested message is already gone."""
    return _MESSAGE_TO_DELETE_NOT_FOUND in str(error).casefold()


def is_message_not_deletable(error: BaseException) -> bool:
    """Return whether Telegram permanently refuses deletion of an old message."""
    normalized = str(error).casefold()
    return any(marker in normalized for marker in _MESSAGE_NOT_DELETABLE_MARKERS)


async def delete_message_idempotently(
    bot: Bot,
    *,
    chat_id: int,
    message_id: int,
) -> DeleteMessageResult:
    """Delete a message without escalating terminal Telegram deletion states."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest as error:
        if is_message_already_absent(error):
            return "already_absent"
        if is_message_not_deletable(error):
            return "not_deletable"
        raise
    return "deleted"


__all__ = (
    "DeleteMessageResult",
    "delete_message_idempotently",
    "is_message_already_absent",
    "is_message_not_deletable",
)
