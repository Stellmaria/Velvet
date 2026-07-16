from __future__ import annotations

from velvet_bot.analytics_dashboard import DashboardPage
from velvet_bot.app.discussion_rankings import build_discussion_ranking_service
from velvet_bot.database import Database


async def list_active_participants(
    database: Database,
    discussion_chat_id: int,
    *,
    period: str,
    page: int,
) -> DashboardPage:
    return await build_discussion_ranking_service(database).list_active_participants(
        discussion_chat_id=discussion_chat_id,
        period=period,
        page=page,
    )


async def list_most_replied_participants(
    database: Database,
    discussion_chat_id: int,
    *,
    period: str,
    page: int,
) -> DashboardPage:
    return await build_discussion_ranking_service(
        database
    ).list_most_replied_participants(
        discussion_chat_id=discussion_chat_id,
        period=period,
        page=page,
    )


async def list_reaction_leaders(
    database: Database,
    discussion_chat_id: int,
    *,
    period: str,
    page: int,
) -> DashboardPage:
    return await build_discussion_ranking_service(database).list_reaction_leaders(
        discussion_chat_id=discussion_chat_id,
        period=period,
        page=page,
    )


async def list_discussed_characters(
    database: Database,
    discussion_chat_id: int,
    parent_channel_id: int,
    *,
    period: str,
    page: int,
) -> DashboardPage:
    return await build_discussion_ranking_service(database).list_discussed_characters(
        discussion_chat_id=discussion_chat_id,
        parent_channel_id=parent_channel_id,
        period=period,
        page=page,
    )


async def list_discussed_universes(
    database: Database,
    discussion_chat_id: int,
    parent_channel_id: int,
    *,
    period: str,
    page: int,
) -> DashboardPage:
    return await build_discussion_ranking_service(database).list_discussed_universes(
        discussion_chat_id=discussion_chat_id,
        parent_channel_id=parent_channel_id,
        period=period,
        page=page,
    )


async def list_discussed_stories(
    database: Database,
    discussion_chat_id: int,
    parent_channel_id: int,
    *,
    period: str,
    page: int,
) -> DashboardPage:
    return await build_discussion_ranking_service(database).list_discussed_stories(
        discussion_chat_id=discussion_chat_id,
        parent_channel_id=parent_channel_id,
        period=period,
        page=page,
    )


__all__ = (
    "list_active_participants",
    "list_discussed_characters",
    "list_discussed_stories",
    "list_discussed_universes",
    "list_most_replied_participants",
    "list_reaction_leaders",
)
