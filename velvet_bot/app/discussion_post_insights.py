from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.discussions.post_insight_repository import (
    DiscussionPostInsightRepository,
)
from velvet_bot.domains.discussions.post_insight_service import (
    DiscussionPostInsightService,
)


def build_discussion_post_insight_service(
    database: Database,
) -> DiscussionPostInsightService:
    return DiscussionPostInsightService(
        DiscussionPostInsightRepository(database)
    )


__all__ = ("build_discussion_post_insight_service",)
