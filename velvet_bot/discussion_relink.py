from __future__ import annotations

from velvet_bot.app.discussion_relink import build_discussion_relink_service
from velvet_bot.database import Database
from velvet_bot.domains.discussions.insight_models import RelinkResult


async def rebuild_discussion_threads(
    database: Database,
    discussion_chat_id: int,
) -> RelinkResult:
    return await build_discussion_relink_service(database).rebuild(
        discussion_chat_id
    )


__all__ = ("RelinkResult", "rebuild_discussion_threads")
