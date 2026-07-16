from __future__ import annotations

from datetime import datetime

from aiogram.types import Message

from velvet_bot.app.publication_drafts import build_publication_draft_service
from velvet_bot.database import Database
from velvet_bot.domains.publication import (
    PublicationDraft,
    PublicationDraftPage,
    PublicationRepository,
)
from velvet_bot.infrastructure.telegram import publication_payload_from_message


async def capture_publication_inbox(
    database: Database,
    message: Message,
    *,
    owner_id: int,
) -> None:
    service = build_publication_draft_service(database)
    await service.capture(
        publication_payload_from_message(message, owner_id=owner_id)
    )


async def create_draft_from_message(
    database: Database,
    message: Message,
    *,
    owner_id: int,
    target_chat_id: int,
) -> PublicationDraft:
    service = build_publication_draft_service(database)
    return await service.create_from_payload(
        publication_payload_from_message(message, owner_id=owner_id),
        target_chat_id=target_chat_id,
    )


async def get_publication_draft(
    database: Database,
    draft_id: int,
    *,
    owner_id: int | None = None,
) -> PublicationDraft | None:
    return await PublicationRepository(database).get_draft(
        draft_id,
        owner_id=owner_id,
    )


async def list_publication_drafts(
    database: Database,
    *,
    owner_id: int,
    statuses: tuple[str, ...],
    page: int = 0,
    page_size: int = 6,
) -> PublicationDraftPage:
    return await PublicationRepository(database).list_drafts(
        owner_id=owner_id,
        statuses=statuses,
        page=page,
        page_size=page_size,
    )


async def set_publication_spoiler(
    database: Database,
    draft_id: int,
    *,
    owner_id: int,
    enabled: bool,
) -> PublicationDraft:
    return await build_publication_draft_service(database).set_spoiler(
        draft_id,
        owner_id=owner_id,
        enabled=enabled,
    )


async def update_publication_text(
    database: Database,
    draft_id: int,
    *,
    owner_id: int,
    text: str,
) -> PublicationDraft:
    return await build_publication_draft_service(database).update_text(
        draft_id,
        owner_id=owner_id,
        text=text,
    )


async def schedule_publication(
    database: Database,
    draft_id: int,
    *,
    owner_id: int,
    scheduled_at: datetime,
) -> PublicationDraft:
    return await build_publication_draft_service(database).schedule(
        draft_id,
        owner_id=owner_id,
        scheduled_at=scheduled_at,
    )


async def cancel_publication(
    database: Database,
    draft_id: int,
    *,
    owner_id: int,
) -> PublicationDraft:
    return await build_publication_draft_service(database).cancel(
        draft_id,
        owner_id=owner_id,
    )


async def retry_publication(
    database: Database,
    draft_id: int,
    *,
    owner_id: int,
) -> PublicationDraft:
    return await build_publication_draft_service(database).retry(
        draft_id,
        owner_id=owner_id,
    )


__all__ = (
    "cancel_publication",
    "capture_publication_inbox",
    "create_draft_from_message",
    "get_publication_draft",
    "list_publication_drafts",
    "retry_publication",
    "schedule_publication",
    "set_publication_spoiler",
    "update_publication_text",
)
