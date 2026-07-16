from __future__ import annotations

from velvet_bot.app.discussion_insights import build_discussion_insight_service
from velvet_bot.database import Database
from velvet_bot.domains.discussions.insight_models import DiscussionSummary


async def get_discussion_summary(
    database: Database,
    discussion_chat_id: int,
    parent_channel_id: int,
    *,
    period: str,
) -> DiscussionSummary:
    return await build_discussion_insight_service(database).get_summary(
        discussion_chat_id=discussion_chat_id,
        parent_channel_id=parent_channel_id,
        period=period,
    )


__all__ = ("DiscussionSummary", "get_discussion_summary")
