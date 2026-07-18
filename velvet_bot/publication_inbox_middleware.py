from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import Message, TelegramObject

from velvet_bot.access import AccessPolicy
from velvet_bot.database import Database
from velvet_bot.publication_workflow import capture_publication_inbox

logger = logging.getLogger(__name__)
_MARKER_RE = re.compile(r"PUBLICATION_(?:SCHEDULE|TEXT):\d+")


class PublicationInboxMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            await self._capture(event, data)
        return await handler(event, data)

    async def _capture(self, message: Message, data: dict[str, Any]) -> None:
        if message.chat.type != ChatType.PRIVATE or message.from_user is None:
            return
        access_policy = data.get("access_policy")
        database = data.get("database")
        if not isinstance(access_policy, AccessPolicy) or not isinstance(database, Database):
            return
        if not access_policy.allows_user(message.from_user):
            return

        text = message.text or message.caption or ""
        if text.lstrip().startswith("/"):
            return
        reply_text = ""
        if message.reply_to_message is not None:
            reply_text = (
                message.reply_to_message.text
                or message.reply_to_message.caption
                or ""
            )
        if _MARKER_RE.search(reply_text):
            return

        try:
            await capture_publication_inbox(
                database,
                message,
                owner_id=message.from_user.id,
            )
        except Exception:  # p2-approved-boundary: best-effort-publication-inbox-capture
            logger.exception(
                "Failed to capture publication inbox item chat=%s message=%s",
                message.chat.id,
                message.message_id,
            )
