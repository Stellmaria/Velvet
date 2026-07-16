from __future__ import annotations

from velvet_bot.analytics_dashboard import DashboardPage
from velvet_bot.app.discussion_activity import build_discussion_activity_service
from velvet_bot.database import Database
from velvet_bot.domains.discussions.insight_models import (
    ActivityBreakdown,
    ActivitySpike,
)


async def list_publications_without_comments(
    database: Database,
    discussion_chat_id: int,
    parent_channel_id: int,
    *,
    period: str,
    page: int,
    page_size: int = 8,
) -> DashboardPage:
    return await build_discussion_activity_service(
        database
    ).list_publications_without_comments(
        discussion_chat_id=discussion_chat_id,
        parent_channel_id=parent_channel_id,
        period=period,
        page=page,
        page_size=page_size,
    )


async def get_activity_breakdown(
    database: Database,
    discussion_chat_id: int,
    *,
    period: str,
    timezone_name: str,
) -> ActivityBreakdown:
    return await build_discussion_activity_service(database).get_activity_breakdown(
        discussion_chat_id=discussion_chat_id,
        period=period,
        timezone_name=timezone_name,
    )


async def list_activity_spikes(
    database: Database,
    discussion_chat_id: int,
    *,
    period: str,
    timezone_name: str,
) -> list[ActivitySpike]:
    return await build_discussion_activity_service(database).list_activity_spikes(
        discussion_chat_id=discussion_chat_id,
        period=period,
        timezone_name=timezone_name,
    )


__all__ = (
    "ActivityBreakdown",
    "ActivitySpike",
    "get_activity_breakdown",
    "list_activity_spikes",
    "list_publications_without_comments",
)
