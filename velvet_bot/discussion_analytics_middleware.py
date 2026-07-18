from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import Message, TelegramObject

from velvet_bot.discussion_ingest import ingest_live_discussion_message

logger = logging.getLogger(__name__)


class DiscussionAnalyticsMiddleware(BaseMiddleware):
    """Capture tracked discussion messages without consuming their handlers."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.chat.type in {
            ChatType.GROUP,
            ChatType.SUPERGROUP,
        }:
            text = event.text or event.caption or ""
            is_command = text.lstrip().startswith("/")
            if not is_command:
                database = data.get("database")
                if database is not None:
                    try:
                        await ingest_live_discussion_message(database, event)
                    except Exception:  # p2-approved-boundary: isolate-discussion-analytics-ingest
                        logger.exception(
                            "Failed to capture discussion message chat=%s message=%s",
                            event.chat.id,
                            event.message_id,
                        )
        return await handler(event, data)


__all__ = ("DiscussionAnalyticsMiddleware",)
