from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.discussions.insight_repository import DiscussionInsightRepository
from velvet_bot.domains.discussions.insight_service import DiscussionInsightService


def build_discussion_insight_service(
    database: Database,
) -> DiscussionInsightService:
    return DiscussionInsightService(DiscussionInsightRepository(database))


__all__ = ("build_discussion_insight_service",)
