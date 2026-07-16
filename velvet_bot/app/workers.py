from __future__ import annotations

from functools import partial

from aiogram import Bot

from velvet_bot.backup_runtime import BackupService
from velvet_bot.database import Database
from velvet_bot.domains.media_quality import MediaQualityRepository, MediaQualityService
from velvet_bot.workers import PeriodicWorkerSpec, WorkerManager
from velvet_bot.workers.iterations import (
    process_backup_once,
    process_due_publications_once,
    process_public_notifications_once,
)


def build_worker_manager(
    *,
    bot: Bot,
    database: Database,
    backup_service: BackupService,
) -> WorkerManager:
    """Build the complete periodic-worker registry for the application."""
    media_quality_service = MediaQualityService(
        bot=bot,
        repository=MediaQualityRepository(database),
    )

    manager = WorkerManager()
    manager.register(
        PeriodicWorkerSpec(
            name="public-archive-notifications",
            description="Уведомления открытого архива",
            interval_seconds=5,
            runner=partial(process_public_notifications_once, bot, database),
        )
    )
    manager.register(
        PeriodicWorkerSpec(
            name="publication-queue",
            description="Очередь публикаций",
            interval_seconds=15,
            runner=partial(process_due_publications_once, bot, database),
        )
    )
    manager.register(
        PeriodicWorkerSpec(
            name="media-quality",
            description="Дубли и проверка медиа",
            interval_seconds=4,
            runner=media_quality_service.process_once,
        )
    )
    manager.register(
        PeriodicWorkerSpec(
            name="postgresql-backups",
            description="Автоматические копии PostgreSQL",
            interval_seconds=300,
            runner=partial(process_backup_once, backup_service, database),
        )
    )
    return manager


__all__ = ("build_worker_manager",)
