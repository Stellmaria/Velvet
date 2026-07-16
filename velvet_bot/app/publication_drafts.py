from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.publication.draft_repository import PublicationDraftRepository
from velvet_bot.domains.publication.draft_service import PublicationDraftService
from velvet_bot.domains.publication.repository import PublicationRepository
from velvet_bot.publication_validation import build_publication_validation_service


def build_publication_draft_service(database: Database) -> PublicationDraftService:
    validation = build_publication_validation_service(database)

    async def validator(draft_id: int, owner_id: int):
        return await validation.validate(draft_id, owner_id=owner_id)

    return PublicationDraftService(
        drafts=PublicationRepository(database),
        commands=PublicationDraftRepository(database),
        validator=validator,
    )


__all__ = ("build_publication_draft_service",)
