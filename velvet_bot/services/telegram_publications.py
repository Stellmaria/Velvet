from __future__ import annotations

from aiogram.types import Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.publication_workflow import PublicationDraft, create_draft_from_message


async def create_publication_draft(
    database: Database,
    source: Message,
    *,
    analytics_channel_ids: frozenset[int],
    owner_id: int,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    target_chat_id: int | None = None,
) -> PublicationDraft:
    destination = target_chat_id
    if destination is None:
        if not analytics_channel_ids:
            raise ValueError("Основной канал публикаций не настроен.")
        destination = sorted(analytics_channel_ids)[0]
    return await create_draft_from_message(
        database,
        source,
        owner_id=owner_id,
        target_chat_id=int(destination),
        workspace_id=workspace_id,
    )


__all__ = ("create_publication_draft",)
