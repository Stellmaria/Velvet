from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from velvet_bot.domains.publication.models import PublicationDraft
from velvet_bot.domains.publication.repository import PublicationRepository
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID

logger = logging.getLogger(__name__)

DraftValidator = Callable[..., Awaitable[PublicationDraft]]


class PublicationDelivery(Protocol):
    async def send(self, draft: PublicationDraft) -> list[int]: ...


class PublicationService:
    """Coordinate validation, state transitions and workspace-safe delivery."""

    def __init__(
        self,
        *,
        repository: PublicationRepository,
        delivery: PublicationDelivery,
        validator: DraftValidator,
    ) -> None:
        self._repository = repository
        self._delivery = delivery
        self._validator = validator

    async def _validate(
        self,
        draft_id: int,
        owner_id: int,
        workspace_id: int,
    ) -> PublicationDraft:
        if int(workspace_id) == DEFAULT_WORKSPACE_ID:
            return await self._validator(draft_id, owner_id)
        return await self._validator(draft_id, owner_id, workspace_id)

    async def _get_draft(
        self,
        draft_id: int,
        *,
        owner_id: int | None,
        workspace_id: int | None,
    ) -> PublicationDraft | None:
        if workspace_id == DEFAULT_WORKSPACE_ID:
            return await self._repository.get_draft(draft_id, owner_id=owner_id)
        return await self._repository.get_draft(
            draft_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )

    async def publish(
        self,
        draft_id: int,
        *,
        owner_id: int | None = None,
        actor_id: int | None = None,
        workspace_id: int | None = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraft:
        draft = await self._get_draft(
            draft_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )
        if draft is None:
            raise ValueError("Черновик не найден в выбранном пространстве.")

        if hasattr(draft, "workspace_id"):
            resolved_workspace_id = int(draft.workspace_id)
        else:
            resolved_workspace_id = DEFAULT_WORKSPACE_ID
        if owner_id is not None:
            draft = await self._validate(draft_id, owner_id, resolved_workspace_id)
        if draft.validation_error_count:
            raise ValueError("Публикация заблокирована ошибками проверки.")
        if draft.status == "published":
            return draft

        if resolved_workspace_id == DEFAULT_WORKSPACE_ID:
            claimed = await self._repository.claim_for_publishing(draft_id)
        else:
            claimed = await self._repository.claim_for_publishing(
                draft_id,
                workspace_id=resolved_workspace_id,
            )
        if not claimed:
            current = await self._get_draft(
                draft_id,
                owner_id=owner_id,
                workspace_id=resolved_workspace_id,
            )
            if current is not None and current.status == "published":
                return current
            raise ValueError("Черновик уже обрабатывается или отменён.")

        try:
            refreshed = await self._get_draft(
                draft_id,
                owner_id=owner_id,
                workspace_id=resolved_workspace_id,
            )
            if refreshed is None:
                raise RuntimeError("Черновик исчез перед публикацией.")
            message_ids = await self._delivery.send(refreshed)
            if resolved_workspace_id == DEFAULT_WORKSPACE_ID:
                await self._repository.mark_published(
                    draft_id,
                    message_ids=message_ids,
                    actor_id=actor_id,
                )
            else:
                await self._repository.mark_published(
                    draft_id,
                    message_ids=message_ids,
                    actor_id=actor_id,
                    workspace_id=resolved_workspace_id,
                )
        except Exception as error:  # p2-approved-boundary: compensate-claimed-publication
            logger.exception(
                "Publication failed workspace_id=%s draft_id=%s",
                resolved_workspace_id,
                draft_id,
            )
            if resolved_workspace_id == DEFAULT_WORKSPACE_ID:
                await self._repository.mark_error(
                    draft_id,
                    error=error,
                    actor_id=actor_id,
                )
            else:
                await self._repository.mark_error(
                    draft_id,
                    error=error,
                    actor_id=actor_id,
                    workspace_id=resolved_workspace_id,
                )
            raise

        result = await self._get_draft(
            draft_id,
            owner_id=owner_id,
            workspace_id=resolved_workspace_id,
        )
        if result is None:
            raise RuntimeError("Опубликованный черновик не найден.")
        return result

    async def process_due_once(self, *, limit: int = 5) -> int:
        published = 0
        for draft_id in await self._repository.list_due_draft_ids(limit=limit):
            try:
                await self.publish(
                    draft_id,
                    actor_id=None,
                    workspace_id=None,
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # p2-approved-boundary: isolate-scheduled-draft
                logger.exception("Scheduled publication failed draft_id=%s", draft_id)
            else:
                published += 1
        return published


__all__ = ("DraftValidator", "PublicationDelivery", "PublicationService")
