from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

_ALREADY_ABSENT_MARKERS = (
    "message to delete not found",
    "message not found",
    "message_id_invalid",
)


def is_message_already_absent(error: BaseException) -> bool:
    """Return whether Telegram reports that the target message no longer exists."""

    normalized = str(error).casefold()
    return any(marker in normalized for marker in _ALREADY_ABSENT_MARKERS)


async def delete_message_safely(message: Message) -> bool:
    """Delete a message and suppress only the already-absent idempotent case."""

    try:
        await message.delete()
    except TelegramBadRequest as error:
        if not is_message_already_absent(error):
            raise
        return False
    return True


__all__ = ("delete_message_safely", "is_message_already_absent")
