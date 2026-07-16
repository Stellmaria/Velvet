from __future__ import annotations

from aiogram import Bot

from velvet_bot.database import Database
from velvet_bot.domains.publication import PublicationDraft, PublicationRepository, PublicationService
from velvet_bot.infrastructure.telegram import TelegramPublicationDelivery
from velvet_bot.publication_workflow import validate_publication_draft


def build_publication_service(bot: Bot, database: Database) -> PublicationService:
    """Wire the publication domain to the legacy validator and Telegram adapter."""

    async def validator(draft_id: int, owner_id: int) -> PublicationDraft:
        return await validate_publication_draft(
            database,
            draft_id,
            owner_id=owner_id,
        )

    return PublicationService(
        repository=PublicationRepository(database),
        delivery=TelegramPublicationDelivery(bot),
        validator=validator,
    )


__all__ = ("build_publication_service",)
