from __future__ import annotations

from velvet_bot.domains.discussions.insight_models import RelinkResult
from velvet_bot.domains.discussions.relink_repository import (
    DiscussionRelinkRepository,
)


class DiscussionRelinkService:
    """Coordinate an explicit rebuild of discussion roots and thread links."""

    def __init__(self, repository: DiscussionRelinkRepository) -> None:
        self._repository = repository

    async def rebuild(self, discussion_chat_id: int) -> RelinkResult:
        if int(discussion_chat_id) == 0:
            raise ValueError("Не указан чат обсуждения.")
        return await self._repository.rebuild(int(discussion_chat_id))


__all__ = ("DiscussionRelinkService",)
