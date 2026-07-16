from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.discussions import (
    DiscussionIngestRepository,
    DiscussionIngestService,
)


def build_discussion_ingest_service(database: Database) -> DiscussionIngestService:
    return DiscussionIngestService(DiscussionIngestRepository(database))


__all__ = ("build_discussion_ingest_service",)
