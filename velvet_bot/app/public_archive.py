from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.characters import CharacterDirectoryRepository, CharacterDirectoryService
from velvet_bot.domains.public_archive import PublicArchiveRepository, PublicArchiveService
from velvet_bot.domains.public_archive.story_catalog import PublicStoryCatalog
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID


def build_public_archive_service(
    database: Database,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> PublicArchiveService:
    scoped_workspace_id = int(workspace_id)
    return PublicArchiveService(
        repository=PublicArchiveRepository(
            database,
            workspace_id=scoped_workspace_id,
        ),
        characters=CharacterDirectoryService(
            CharacterDirectoryRepository(
                database,
                workspace_id=scoped_workspace_id,
            )
        ),
        stories=PublicStoryCatalog(
            database,
            workspace_id=scoped_workspace_id,
        ),
    )


__all__ = ("build_public_archive_service",)
