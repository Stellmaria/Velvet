from __future__ import annotations

from velvet_bot.analytics_dashboard import normalize_period, period_since
from velvet_bot.domains.discussions.insight_models import DiscussionSummary
from velvet_bot.domains.discussions.insight_repository import DiscussionInsightRepository


class DiscussionInsightService:
    """Coordinate detailed discussion analytics queries."""

    def __init__(self, repository: DiscussionInsightRepository) -> None:
        self._repository = repository

    async def get_summary(
        self,
        *,
        discussion_chat_id: int,
        parent_channel_id: int,
        period: str,
    ) -> DiscussionSummary:
        normalized_period = normalize_period(period)
        return await self._repository.get_summary(
            discussion_chat_id=discussion_chat_id,
            parent_channel_id=parent_channel_id,
            since=period_since(normalized_period),
        )


__all__ = ("DiscussionInsightService",)
