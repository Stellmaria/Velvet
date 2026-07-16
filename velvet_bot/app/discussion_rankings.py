from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.discussions.ranking_repository import (
    DiscussionRankingRepository,
)
from velvet_bot.domains.discussions.ranking_service import DiscussionRankingService


def build_discussion_ranking_service(
    database: Database,
) -> DiscussionRankingService:
    return DiscussionRankingService(DiscussionRankingRepository(database))


__all__ = ("build_discussion_ranking_service",)
