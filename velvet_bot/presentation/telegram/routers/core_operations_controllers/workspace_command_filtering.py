from __future__ import annotations

from aiogram.types import Message


def command_name(message: Message) -> str:
    text = (message.text or message.caption or "").strip()
    if not text.startswith("/"):
        return ""
    token = text.split(maxsplit=1)[0][1:]
    return token.split("@", maxsplit=1)[0].casefold()


__all__ = ("command_name",)
