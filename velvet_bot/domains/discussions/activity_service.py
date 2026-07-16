from __future__ import annotations

import math

from velvet_bot.analytics_dashboard import DashboardPage, normalize_period, period_since
from velvet_bot.domains.discussions.activity_repository import (
    DiscussionActivityRepository,
)
from velvet_bot.domains.discussions.insight_models import (
    ActivityBreakdown,
    ActivitySpike,
)


class DiscussionActivityService:
    """Coordinate silent-publication and temporal activity analytics."""

    def __init__(self, repository: DiscussionActivityRepository) -> None:
        self._repository = repository

    @staticmethod
    def _since(period: str):
        return period_since(normalize_period(period))

    async def list_publications_without_comments(
        self,
        *,
        discussion_chat_id: int,
        parent_channel_id: int,
        period: str,
        page: int,
        page_size: int = 8,
    ) -> DashboardPage:
        return await self._repository.list_publications_without_comments(
            discussion_chat_id=discussion_chat_id,
            parent_channel_id=parent_channel_id,
            since=self._since(period),
            page=page,
            page_size=page_size,
        )

    async def get_activity_breakdown(
        self,
        *,
        discussion_chat_id: int,
        period: str,
        timezone_name: str,
    ) -> ActivityBreakdown:
        return await self._repository.get_activity_breakdown(
            discussion_chat_id=discussion_chat_id,
            since=self._since(period),
            timezone_name=timezone_name,
        )

    async def list_activity_spikes(
        self,
        *,
        discussion_chat_id: int,
        period: str,
        timezone_name: str,
    ) -> list[ActivitySpike]:
        rows = await self._repository.list_daily_activity(
            discussion_chat_id=discussion_chat_id,
            since=self._since(period),
            timezone_name=timezone_name,
        )
        values = [item.comment_count for item in rows]
        if len(values) < 3:
            return []
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        deviation = math.sqrt(variance)
        threshold = max(5.0, mean * 1.8, mean + 2 * deviation)
        spikes = [
            ActivitySpike(
                day=item.day,
                comment_count=item.comment_count,
                baseline=mean,
                ratio=(item.comment_count / mean if mean > 0 else 0.0),
            )
            for item in rows
            if item.comment_count >= threshold
        ]
        return sorted(
            spikes,
            key=lambda item: (-item.comment_count, item.day),
        )[:10]


__all__ = ("DiscussionActivityService",)
