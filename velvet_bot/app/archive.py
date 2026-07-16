from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.archive import ArchiveRepository, ArchiveService


def build_archive_service(database: Database) -> ArchiveService:
    return ArchiveService(ArchiveRepository(database))


__all__ = ("build_archive_service",)
