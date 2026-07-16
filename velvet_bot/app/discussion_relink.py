from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.discussions.relink_repository import (
    DiscussionRelinkRepository,
)
from velvet_bot.domains.discussions.relink_service import DiscussionRelinkService


def build_discussion_relink_service(
    database: Database,
) -> DiscussionRelinkService:
    return DiscussionRelinkService(DiscussionRelinkRepository(database))


__all__ = ("build_discussion_relink_service",)
