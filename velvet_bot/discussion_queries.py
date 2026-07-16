from __future__ import annotations

from velvet_bot.app.discussions import build_discussion_service
from velvet_bot.database import Database
from velvet_bot.domains.discussions import DiscussionOverview, ParticipantStat


async def is_tracked_discussion(database: Database, chat_id: int) -> bool:
    return await build_discussion_service(database).is_tracked(chat_id)


async def get_discussion_overview(
    database: Database,
    chat_id: int,
) -> DiscussionOverview:
    return await build_discussion_service(database).get_overview(chat_id)


async def list_participant_stats(
    database: Database,
    chat_id: int,
    *,
    limit: int = 20,
) -> list[ParticipantStat]:
    return await build_discussion_service(database).list_participant_stats(
        chat_id,
        limit=limit,
    )


async def set_discussion_reaction_counts(
    database: Database,
    *,
    chat_id: int,
    message_id: int,
    breakdown: dict[str, int],
) -> bool:
    return await build_discussion_service(database).set_reaction_counts(
        discussion_chat_id=chat_id,
        discussion_message_id=message_id,
        reaction_breakdown=breakdown,
    )


async def apply_discussion_reaction_delta(
    database: Database,
    *,
    chat_id: int,
    message_id: int,
    delta: dict[str, int],
) -> bool:
    return await build_discussion_service(database).apply_reaction_delta(
        discussion_chat_id=chat_id,
        discussion_message_id=message_id,
        delta=delta,
    )


__all__ = (
    "DiscussionOverview",
    "ParticipantStat",
    "apply_discussion_reaction_delta",
    "get_discussion_overview",
    "is_tracked_discussion",
    "list_participant_stats",
    "set_discussion_reaction_counts",
)
