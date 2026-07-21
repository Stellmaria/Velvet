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
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.publication_validation import build_publication_validation_service


class PublicationActions:
    """Transport-neutral workspace-scoped actions used by publication UI adapters."""

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
        workspace_id: int | None = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraft | None:
        if workspace_id == DEFAULT_WORKSPACE_ID:
            return await self._drafts.get_draft(draft_id, owner_id=owner_id)
        return await self._drafts.get_draft(
            draft_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )

    async def list_drafts(
        self,
        *,
        owner_id: int,
        statuses: tuple[str, ...],
        page: int = 0,
        page_size: int = 6,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraftPage:
        if workspace_id == DEFAULT_WORKSPACE_ID:
            return await self._drafts.list_drafts(
                owner_id=owner_id,
                statuses=statuses,
                page=page,
                page_size=page_size,
            )
        return await self._drafts.list_drafts(
            owner_id=owner_id,
            statuses=statuses,
            page=page,
            page_size=page_size,
            workspace_id=workspace_id,
        )

    async def recheck(
        self,
        draft_id: int,
        *,
        owner_id: int,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraft:
        if workspace_id == DEFAULT_WORKSPACE_ID:
            return await self._validation.validate(draft_id, owner_id=owner_id)
        return await self._validation.validate(
            draft_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )

    async def set_spoiler(
        self,
        draft_id: int,
        *,
        owner_id: int,
        enabled: bool,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraft:
        if workspace_id == DEFAULT_WORKSPACE_ID:
            return await self._commands.set_spoiler(
                draft_id,
                owner_id=owner_id,
                enabled=enabled,
            )
        return await self._commands.set_spoiler(
            draft_id,
            owner_id=owner_id,
            enabled=enabled,
            workspace_id=workspace_id,
        )

    async def update_text(
        self,
        draft_id: int,
        *,
        owner_id: int,
        text: str,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraft:
        if workspace_id == DEFAULT_WORKSPACE_ID:
            return await self._commands.update_text(
                draft_id,
                owner_id=owner_id,
                text=text,
            )
        return await self._commands.update_text(
            draft_id,
            owner_id=owner_id,
            text=text,
            workspace_id=workspace_id,
        )

    async def schedule(
        self,
        draft_id: int,
        *,
        owner_id: int,
        scheduled_at: datetime,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraft:
        if workspace_id == DEFAULT_WORKSPACE_ID:
            return await self._commands.schedule(
                draft_id,
                owner_id=owner_id,
                scheduled_at=scheduled_at,
            )
        return await self._commands.schedule(
            draft_id,
            owner_id=owner_id,
            scheduled_at=scheduled_at,
            workspace_id=workspace_id,
        )

    async def cancel(
        self,
        draft_id: int,
        *,
        owner_id: int,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraft:
        if workspace_id == DEFAULT_WORKSPACE_ID:
            return await self._commands.cancel(draft_id, owner_id=owner_id)
        return await self._commands.cancel(
            draft_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )

    async def retry(
        self,
        draft_id: int,
        *,
        owner_id: int,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraft:
        if workspace_id == DEFAULT_WORKSPACE_ID:
            return await self._commands.retry(draft_id, owner_id=owner_id)
        return await self._commands.retry(
            draft_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )


def build_publication_actions(database: Database) -> PublicationActions:
    return PublicationActions(
        drafts=PublicationRepository(database),
        commands=build_publication_draft_service(database),
        validation=build_publication_validation_service(database),
    )


__all__ = ("PublicationActions", "build_publication_actions")
