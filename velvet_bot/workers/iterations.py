from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot

from velvet_bot import media_quality
from velvet_bot.backup_runtime import BackupService
from velvet_bot.database import Database
from velvet_bot.public_notifications import process_public_notifications_once
from velvet_bot.publication_worker import process_due_publications_once


@dataclass(frozen=True, slots=True)
class MediaQualityIterationResult:
    fingerprint_targets: int
    file_checks: int


async def process_media_quality_once(
    bot: Bot,
    database: Database,
) -> MediaQualityIterationResult:
    """Run one bounded media-quality iteration without owning an endless loop."""
    targets = await media_quality._claim_pending_images(database)
    for target in targets:
        await media_quality.scan_media_target(bot, database, target)

    file_checks = await media_quality._claim_file_checks(database)
    for media_id, file_id in file_checks:
        await media_quality.verify_media_file(bot, database, media_id, file_id)

    return MediaQualityIterationResult(
        fingerprint_targets=len(targets),
        file_checks=len(file_checks),
    )


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
