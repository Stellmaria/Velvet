from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.discussions import DiscussionRepository, DiscussionService


def build_discussion_service(database: Database) -> DiscussionService:
    return DiscussionService(DiscussionRepository(database))


__all__ = ("build_discussion_service",)
