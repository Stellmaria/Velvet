from __future__ import annotations

from aiogram.types import Message

from velvet_bot.database import Database
from velvet_bot.publication_workflow import PublicationDraft, create_draft_from_message


async def create_publication_draft(
    database: Database,
    source: Message,
    *,
    analytics_channel_ids: frozenset[int],
    owner_id: int,
) -> PublicationDraft:
    if not analytics_channel_ids:
        raise ValueError("Основной канал публикаций не настроен.")
    return await create_draft_from_message(
        database,
        source,
        owner_id=owner_id,
        target_chat_id=sorted(analytics_channel_ids)[0],
    )


__all__ = ("create_publication_draft",)
