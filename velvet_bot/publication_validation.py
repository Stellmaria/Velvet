from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.publication import PublicationDraft, PublicationRepository
from velvet_bot.domains.publication.validation_repository import (
    PublicationValidationRepository,
)
from velvet_bot.domains.publication.validation_service import PublicationValidationService
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID


def build_publication_validation_service(
    database: Database,
) -> PublicationValidationService:
    drafts = PublicationRepository(database)
    return PublicationValidationService(
        drafts=drafts,
        validation=PublicationValidationRepository(database),
    )


async def validate_publication_draft(
    database: Database,
    draft_id: int,
    *,
    owner_id: int,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> PublicationDraft:
    return await build_publication_validation_service(database).validate(
        draft_id,
        owner_id=owner_id,
        workspace_id=workspace_id,
    )


__all__ = (
    "build_publication_validation_service",
    "validate_publication_draft",
)
