from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message


async def delete_message_safely(message: Message) -> bool:
    """Delete a message best-effort while keeping unrelated failures visible."""

    try:
        await message.delete()
    except TelegramBadRequest:
        return False
    return True


__all__ = ("delete_message_safely",)
