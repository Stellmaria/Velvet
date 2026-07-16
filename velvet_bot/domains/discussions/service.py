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
        reaction_counts: dict[str, int],
    ) -> None:
        await self._repository.set_reaction_counts(
            discussion_chat_id=discussion_chat_id,
            discussion_message_id=discussion_message_id,
            reaction_counts=reaction_counts,
        )

    async def apply_reaction_delta(
        self,
        *,
        discussion_chat_id: int,
        discussion_message_id: int,
        reaction_key: str,
        delta: int,
    ) -> None:
        cleaned_key = reaction_key.strip()
        if not cleaned_key:
            raise ValueError("Пустая реакция недопустима.")
        if delta == 0:
            return
        await self._repository.apply_reaction_delta(
            discussion_chat_id=discussion_chat_id,
            discussion_message_id=discussion_message_id,
            reaction_key=cleaned_key,
            delta=delta,
        )

    async def get_overview(
        self,
        discussion_chat_id: int,
    ) -> DiscussionOverview | None:
        return await self._repository.get_overview(discussion_chat_id)

    async def list_participant_stats(
        self,
        discussion_chat_id: int,
        *,
        limit: int = 10,
    ) -> list[ParticipantStat]:
        return await self._repository.list_participant_stats(
            discussion_chat_id,
            limit=limit,
        )


__all__ = ("DiscussionService",)
