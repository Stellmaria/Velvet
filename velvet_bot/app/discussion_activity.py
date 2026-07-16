from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.discussions.activity_repository import (
    DiscussionActivityRepository,
)
from velvet_bot.domains.discussions.activity_service import DiscussionActivityService


def build_discussion_activity_service(
    database: Database,
) -> DiscussionActivityService:
    return DiscussionActivityService(DiscussionActivityRepository(database))


__all__ = ("build_discussion_activity_service",)
