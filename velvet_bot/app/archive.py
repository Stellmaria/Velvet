from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.archive import ArchiveRepository, ArchiveService
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID


def build_archive_service(
    database: Database,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> ArchiveService:
    return ArchiveService(
        ArchiveRepository(database, workspace_id=int(workspace_id))
    )


__all__ = ("build_archive_service",)
