from __future__ import annotations

from velvet_bot.app.discussions import build_discussion_service
from velvet_bot.database import Database
from velvet_bot.domains.discussions import DiscussionOverview, ParticipantStat


async def is_tracked_discussion(database: Database, chat_id: int) -> bool:
    return await build_discussion_service(database).is_tracked(chat_id)


async def get_discussion_overview(
    database: Database,
    discussion_chat_id: int,
) -> DiscussionOverview | None:
    return await build_discussion_service(database).get_overview(discussion_chat_id)


async def list_participant_stats(
    database: Database,
    discussion_chat_id: int,
    *,
    limit: int = 10,
) -> list[ParticipantStat]:
    return await build_discussion_service(database).list_participant_stats(
        discussion_chat_id,
        limit=limit,
    )


async def set_discussion_reaction_counts(
    database: Database,
    *,
    discussion_chat_id: int,
    discussion_message_id: int,
    reaction_counts: dict[str, int],
) -> None:
    await build_discussion_service(database).set_reaction_counts(
        discussion_chat_id=discussion_chat_id,
        discussion_message_id=discussion_message_id,
        reaction_counts=reaction_counts,
    )


async def apply_discussion_reaction_delta(
    database: Database,
    *,
    discussion_chat_id: int,
    discussion_message_id: int,
    reaction_key: str,
    delta: int,
) -> None:
    await build_discussion_service(database).apply_reaction_delta(
        discussion_chat_id=discussion_chat_id,
        discussion_message_id=discussion_message_id,
        reaction_key=reaction_key,
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
