from __future__ import annotations

from velvet_bot.domains.discussions.models import DiscussionOverview, ParticipantStat
from velvet_bot.domains.discussions.repository import DiscussionRepository


class DiscussionService:
    """Coordinate tracked discussion reports and reaction updates."""

    def __init__(self, repository: DiscussionRepository) -> None:
        self._repository = repository

    async def is_tracked(self, chat_id: int) -> bool:
        return await self._repository.is_tracked(chat_id)

    async def set_reaction_counts(
        self,
        *,
        discussion_chat_id: int,
        discussion_message_id: int,
        reaction_breakdown: dict[str, int],
    ) -> bool:
        return await self._repository.set_reaction_counts(
            discussion_chat_id=discussion_chat_id,
            discussion_message_id=discussion_message_id,
            reaction_breakdown=reaction_breakdown,
        )

    async def apply_reaction_delta(
        self,
        *,
        discussion_chat_id: int,
        discussion_message_id: int,
        delta: dict[str, int],
    ) -> bool:
        normalized = {
            str(key).strip(): int(value)
            for key, value in delta.items()
            if str(key).strip() and int(value) != 0
        }
        if not normalized:
            return False
        return await self._repository.apply_reaction_delta(
            discussion_chat_id=discussion_chat_id,
            discussion_message_id=discussion_message_id,
            delta=normalized,
        )

    async def get_overview(self, chat_id: int) -> DiscussionOverview | None:
        return await self._repository.get_overview(chat_id)

    async def list_participant_stats(
        self,
        chat_id: int,
        *,
        limit: int = 20,
    ) -> list[ParticipantStat]:
        return await self._repository.list_participant_stats(
            chat_id,
            limit=limit,
        )


__all__ = ("DiscussionService",)
