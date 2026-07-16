from __future__ import annotations

from aiogram.types import Message

from velvet_bot.app.discussion_ingest import build_discussion_ingest_service
from velvet_bot.database import Database
from velvet_bot.infrastructure.telegram.discussion_events import (
    discussion_event_from_message,
)


async def ingest_live_discussion_message(
    database: Database,
    message: Message,
) -> bool:
    result = await build_discussion_ingest_service(database).ingest(
        discussion_event_from_message(message)
    )
    return result.stored


__all__ = ("ingest_live_discussion_message",)
