from __future__ import annotations

from aiogram import Bot

from velvet_bot.backup_runtime import BackupService
from velvet_bot.database import Database
from velvet_bot.domains.media_quality import (
    MediaQualityRepository,
    MediaQualityRunResult,
    MediaQualityService,
)
from velvet_bot.public_notifications import process_public_notifications_once
from velvet_bot.publication_worker import process_due_publications_once

MediaQualityIterationResult = MediaQualityRunResult


async def process_media_quality_once(
    bot: Bot,
    database: Database,
) -> MediaQualityIterationResult:
    """Backward-compatible one-shot entrypoint for the media-quality domain."""
    service = MediaQualityService(
        bot=bot,
        repository=MediaQualityRepository(database),
    )
    return await service.process_once()


async def process_backup_once(
    backup_service: BackupService,
    database: Database,
):
    return await backup_service.run_scheduled_if_due(database)


__all__ = (
    "MediaQualityIterationResult",
    "process_backup_once",
    "process_due_publications_once",
    "process_media_quality_once",
    "process_public_notifications_once",
)
