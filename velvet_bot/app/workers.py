from __future__ import annotations

from functools import partial

from aiogram import Bot

from velvet_bot.app.public_notifications import build_public_notification_dispatcher
from velvet_bot.app.publication import build_publication_service
from velvet_bot.backup_runtime import BackupService
from velvet_bot.core.config import Settings
from velvet_bot.database import Database
from velvet_bot.domains.media_quality import MediaQualityRepository, MediaQualityService
from velvet_bot.error_center import ErrorIncidentCenter
from velvet_bot.ollama_vision import ReliableVisionClient
from velvet_bot.resilient_ai_vision import (
    ResilientMediaAIRepository,
    ResilientMediaAIVisionService,
)
from velvet_bot.workers import PeriodicWorkerSpec, WorkerManager
from velvet_bot.workers.iterations import process_backup_once


def build_worker_manager(
    *,
    bot: Bot,
    database: Database,
    backup_service: BackupService,
    settings: Settings | None = None,
    error_center: ErrorIncidentCenter | None = None,
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
    if settings is not None and settings.ai_vision_enabled:
        ai_service = ResilientMediaAIVisionService(
            bot=bot,
            repository=ResilientMediaAIRepository(database),
            client=ReliableVisionClient(
                provider=settings.ai_vision_provider,
                base_url=settings.ai_vision_base_url,
                model=settings.ai_vision_model,
                api_key=settings.ai_vision_api_key,
                timeout_seconds=settings.ai_vision_timeout_seconds,
            ),
            max_attempts=settings.ai_vision_max_attempts,
        )
        manager.register(
            PeriodicWorkerSpec(
                name="ai-vision",
                description="Смысловой ИИ-анализ изображений",
                interval_seconds=8,
                runner=ai_service.process_once,
            )
        )
    if error_center is not None:
        manager.register(
            PeriodicWorkerSpec(
                name="error-alert-reminders",
                description="Напоминания владельцу о непросмотренных ошибках",
                interval_seconds=300,
                runner=error_center.send_owner_reminder_once,
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
