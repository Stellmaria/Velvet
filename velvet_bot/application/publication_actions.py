from __future__ import annotations

from datetime import datetime

from velvet_bot.app.publication_drafts import build_publication_draft_service
from velvet_bot.database import Database
from velvet_bot.domains.publication import (
    PublicationDraft,
    PublicationDraftPage,
    PublicationRepository,
)
from velvet_bot.domains.publication.draft_service import PublicationDraftService
from velvet_bot.domains.publication.validation_service import PublicationValidationService
from velvet_bot.publication_validation import build_publication_validation_service


class PublicationActions:
    """Transport-neutral actions used by publication UI adapters."""

    def __init__(
        self,
        *,
        drafts: PublicationRepository,
        commands: PublicationDraftService,
        validation: PublicationValidationService,
    ) -> None:
        self._drafts = drafts
        self._commands = commands
        self._validation = validation

    async def get_draft(
        self,
        draft_id: int,
        *,
        owner_id: int | None = None,
    ) -> PublicationDraft | None:
        return await self._drafts.get_draft(draft_id, owner_id=owner_id)

    async def list_drafts(
        self,
        *,
        owner_id: int,
        statuses: tuple[str, ...],
        page: int = 0,
        page_size: int = 6,
    ) -> PublicationDraftPage:
        return await self._drafts.list_drafts(
            owner_id=owner_id,
            statuses=statuses,
            page=page,
            page_size=page_size,
        )

    async def recheck(self, draft_id: int, *, owner_id: int) -> PublicationDraft:
        return await self._validation.validate(draft_id, owner_id=owner_id)

    async def set_spoiler(
        self,
        draft_id: int,
        *,
        owner_id: int,
        enabled: bool,
    ) -> PublicationDraft:
        return await self._commands.set_spoiler(
            draft_id,
            owner_id=owner_id,
            enabled=enabled,
        )

    async def update_text(
        self,
        draft_id: int,
        *,
        owner_id: int,
        text: str,
    ) -> PublicationDraft:
        return await self._commands.update_text(
            draft_id,
            owner_id=owner_id,
            text=text,
        )

    async def schedule(
        self,
        draft_id: int,
        *,
        owner_id: int,
        scheduled_at: datetime,
    ) -> PublicationDraft:
        return await self._commands.schedule(
            draft_id,
            owner_id=owner_id,
            scheduled_at=scheduled_at,
        )

    async def cancel(self, draft_id: int, *, owner_id: int) -> PublicationDraft:
        return await self._commands.cancel(draft_id, owner_id=owner_id)

    async def retry(self, draft_id: int, *, owner_id: int) -> PublicationDraft:
        return await self._commands.retry(draft_id, owner_id=owner_id)


def build_publication_actions(database: Database) -> PublicationActions:
    return PublicationActions(
        drafts=PublicationRepository(database),
        commands=build_publication_draft_service(database),
        validation=build_publication_validation_service(database),
    )


__all__ = ("PublicationActions", "build_publication_actions")
