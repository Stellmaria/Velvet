from __future__ import annotations

from velvet_bot.analytics_dashboard import normalize_period, period_since
from velvet_bot.domains.discussions.insight_models import (
    DiscussedPost,
    DiscussedPostPage,
)
from velvet_bot.domains.discussions.post_insight_repository import (
    DiscussionPostInsightRepository,
)


class DiscussionPostInsightService:
    """Coordinate discussed-publication analytics queries."""

    def __init__(self, repository: DiscussionPostInsightRepository) -> None:
        self._repository = repository

    async def list_posts(
        self,
        *,
        discussion_chat_id: int,
        parent_channel_id: int,
        period: str,
        page: int,
        page_size: int = 6,
    ) -> DiscussedPostPage:
        normalized_period = normalize_period(period)
        return await self._repository.list_posts(
            discussion_chat_id=discussion_chat_id,
            parent_channel_id=parent_channel_id,
            since=period_since(normalized_period),
            page=page,
            page_size=page_size,
        )

    async def get_post(
        self,
        *,
        discussion_chat_id: int,
        parent_channel_id: int,
        post_id: int,
        period: str,
    ) -> DiscussedPost | None:
        normalized_period = normalize_period(period)
        return await self._repository.get_post(
            discussion_chat_id=discussion_chat_id,
            parent_channel_id=parent_channel_id,
            post_id=post_id,
            since=period_since(normalized_period),
        )


__all__ = ("DiscussionPostInsightService",)
