from __future__ import annotations

from aiogram import Bot

from velvet_bot.database import Database
from velvet_bot.domains.publication import PublicationDraft, PublicationRepository, PublicationService
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.infrastructure.telegram import TelegramPublicationDelivery
from velvet_bot.publication_validation import build_publication_validation_service


def build_publication_service(bot: Bot, database: Database) -> PublicationService:
    """Wire publication persistence, validation and Telegram delivery."""
    validation_service = build_publication_validation_service(database)

    async def validator(
        draft_id: int,
        owner_id: int,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraft:
        return await validation_service.validate(
            draft_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )

    return PublicationService(
        repository=PublicationRepository(database),
        delivery=TelegramPublicationDelivery(bot),
        validator=validator,
    )


__all__ = ("build_publication_service",)
