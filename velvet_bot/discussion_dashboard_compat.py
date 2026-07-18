from __future__ import annotations

from velvet_bot.analytics_dashboard import (
    DiscussionDashboard,
    get_discussion_dashboard,
)
from velvet_bot.database import Database


async def get_discussion_dashboard_compat(
    database: Database,
    chat_id: int,
    *,
    period: str,
) -> DiscussionDashboard:
    return await get_discussion_dashboard(
        database,
        int(chat_id),
        period=period,
    )


__all__ = ("get_discussion_dashboard_compat",)
