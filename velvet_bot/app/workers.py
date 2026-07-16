from __future__ import annotations

from functools import partial

from aiogram import Bot

from velvet_bot.app.public_notifications import build_public_notification_dispatcher
from velvet_bot.app.publication import build_publication_service
from velvet_bot.backup_runtime import BackupService
from velvet_bot.database import Database
from velvet_bot.domains.media_quality import MediaQualityRepository, MediaQualityService
from velvet_bot.workers import PeriodicWorkerSpec, WorkerManager
from velvet_bot.workers.iterations import process_backup_once


def build_worker_manager(
    *,
    bot: Bot,
    database: Database,
    backup_service: BackupService,
) -> WorkerManager:
    """Build the complete periodic-worker registry for the application."""
    public_notifications = build_public_notification_dispatcher(bot, database)
    publication_service = build_publication_service(bot, database)
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
            runner=public_notifications.process_once,
        )
    )
    manager.register(
        PeriodicWorkerSpec(
            name="publication-queue",
            description="Очередь публикаций",
            interval_seconds=15,
            runner=publication_service.process_due_once,
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
