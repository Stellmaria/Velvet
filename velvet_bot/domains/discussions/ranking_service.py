from __future__ import annotations

from velvet_bot.analytics_dashboard import DashboardPage, normalize_period, period_since
from velvet_bot.domains.discussions.ranking_repository import (
    DiscussionRankingRepository,
)


class DiscussionRankingService:
    """Coordinate paginated discussion rankings."""

    def __init__(self, repository: DiscussionRankingRepository) -> None:
        self._repository = repository

    @staticmethod
    def _since(period: str):
        return period_since(normalize_period(period))

    async def list_active_participants(
        self, *, discussion_chat_id: int, period: str, page: int
    ) -> DashboardPage:
        return await self._repository.list_active_participants(
            discussion_chat_id=discussion_chat_id,
            since=self._since(period),
            page=page,
        )

    async def list_most_replied_participants(
        self, *, discussion_chat_id: int, period: str, page: int
    ) -> DashboardPage:
        return await self._repository.list_most_replied_participants(
            discussion_chat_id=discussion_chat_id,
            since=self._since(period),
            page=page,
        )

    async def list_reaction_leaders(
        self, *, discussion_chat_id: int, period: str, page: int
    ) -> DashboardPage:
        return await self._repository.list_reaction_leaders(
            discussion_chat_id=discussion_chat_id,
            since=self._since(period),
            page=page,
        )

    async def list_discussed_characters(
        self,
        *,
        discussion_chat_id: int,
        parent_channel_id: int,
        period: str,
        page: int,
    ) -> DashboardPage:
        return await self._repository.list_discussed_characters(
            discussion_chat_id=discussion_chat_id,
            parent_channel_id=parent_channel_id,
            since=self._since(period),
            page=page,
        )

    async def list_discussed_universes(
        self,
        *,
        discussion_chat_id: int,
        parent_channel_id: int,
        period: str,
        page: int,
    ) -> DashboardPage:
        return await self._repository.list_discussed_universes(
            discussion_chat_id=discussion_chat_id,
            parent_channel_id=parent_channel_id,
            since=self._since(period),
            page=page,
        )

    async def list_discussed_stories(
        self,
        *,
        discussion_chat_id: int,
        parent_channel_id: int,
        period: str,
        page: int,
    ) -> DashboardPage:
        return await self._repository.list_discussed_stories(
            discussion_chat_id=discussion_chat_id,
            parent_channel_id=parent_channel_id,
            since=self._since(period),
            page=page,
        )


__all__ = ("DiscussionRankingService",)
