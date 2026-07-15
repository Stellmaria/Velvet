from __future__ import annotations

import logging
from html import escape
from typing import Any

from aiogram import Bot

logger = logging.getLogger(__name__)

_LEVEL_EMOJI = {
    "INFO": "ℹ️",
    "SUCCESS": "✅",
    "WARNING": "⚠️",
    "ERROR": "❌",
}


class TelegramAuditLogger:
    """Send compact operational events to a private Telegram log chat."""

    def __init__(self, bot: Bot, chat_id: int | None) -> None:
        self.bot = bot
        self.chat_id = chat_id

    async def send(
        self,
        event_title: str,
        *,
        level: str = "INFO",
        **fields: Any,
    ) -> None:
        if self.chat_id is None:
            return

        normalized_level = level.upper()
        emoji = _LEVEL_EMOJI.get(normalized_level, "•")
        lines = [f"<b>{emoji} {escape(event_title)}</b>"]
        for name, value in fields.items():
            if value is None or value == "":
                continue
            label = escape(str(name).replace("_", " ").capitalize())
            rendered = escape(str(value))
            lines.append(f"<b>{label}:</b> <code>{rendered}</code>")

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3990] + "\n…"

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                disable_web_page_preview=True,
            )
        except Exception:
            # Never let a broken log destination break the archive itself.
            logger.exception("Failed to send Telegram audit event: %s", event_title)

    async def error(
        self,
        event_title: str,
        error: BaseException | str,
        **fields: Any,
    ) -> None:
        await self.send(
            event_title,
            level="ERROR",
            error=str(error),
            **fields,
        )
