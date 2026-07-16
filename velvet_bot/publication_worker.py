from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from velvet_bot.app.publication import build_publication_service
from velvet_bot.database import Database
from velvet_bot.domains.publication import PublicationDraft, PublicationRepository
from velvet_bot.infrastructure.telegram.publication_delivery import (
    TelegramPublicationDelivery,
    split_publication_text,
)

logger = logging.getLogger(__name__)


async def send_publication(bot: Bot, draft: PublicationDraft) -> list[int]:
    """Backward-compatible Telegram delivery entrypoint."""
    return await TelegramPublicationDelivery(bot).send(draft)


async def publish_publication_draft(
    bot: Bot,
    database: Database,
    draft_id: int,
    *,
    owner_id: int | None = None,
    actor_id: int | None = None,
) -> PublicationDraft:
    return await build_publication_service(bot, database).publish(
        draft_id,
        owner_id=owner_id,
        actor_id=actor_id,
    )


async def _due_publication_ids(database: Database, *, limit: int = 5) -> list[int]:
    return await PublicationRepository(database).list_due_draft_ids(limit=limit)


async def process_due_publications_once(
    bot: Bot,
    database: Database,
    *,
    limit: int = 5,
) -> int:
    return await build_publication_service(bot, database).process_due_once(limit=limit)


async def run_publication_worker(
    bot: Bot,
    database: Database,
    *,
    interval_seconds: float = 15.0,
) -> None:
    """Backward-compatible standalone publication loop."""
    service = build_publication_service(bot, database)
    while True:
        try:
            await service.process_due_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Publication queue loop failed")
        await asyncio.sleep(interval_seconds)


__all__ = (
    "build_publication_service",
    "process_due_publications_once",
    "publish_publication_draft",
    "run_publication_worker",
    "send_publication",
    "split_publication_text",
)
