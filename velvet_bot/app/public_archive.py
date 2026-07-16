from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.characters import CharacterDirectoryRepository, CharacterDirectoryService
from velvet_bot.domains.public_archive import PublicArchiveRepository, PublicArchiveService
from velvet_bot.domains.stories import StoryRepository, StoryService


def build_public_archive_service(database: Database) -> PublicArchiveService:
    return PublicArchiveService(
        repository=PublicArchiveRepository(database),
        characters=CharacterDirectoryService(CharacterDirectoryRepository(database)),
        stories=StoryService(StoryRepository(database)),
    )


__all__ = ("build_public_archive_service",)
