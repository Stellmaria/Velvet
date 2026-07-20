from __future__ import annotations

import asyncio
import os
from functools import partial
from typing import Awaitable, Callable

from aiogram import Bot

from velvet_bot.ai_quality import QualityVisionClient
from velvet_bot.app.public_notifications import build_public_notification_dispatcher
from velvet_bot.app.publication import build_publication_service
from velvet_bot.backup_runtime import BackupService
from velvet_bot.calibrated_ai_quality import CalibratedAIQualityService
from velvet_bot.core.config import Settings
from velvet_bot.database import Database
from velvet_bot.domains.media_quality import MediaQualityRepository, MediaQualityService
from velvet_bot.domains.watermark.repository import WatermarkRepository
from velvet_bot.domains.watermark.service import WatermarkService
from velvet_bot.error_center import ErrorIncidentCenter
from velvet_bot.infrastructure.krita_bridge import KritaBridge, default_krita_bridge_dir
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.ollama_vision import ReliableVisionClient
from velvet_bot.quality_calibration import QualityCalibrationRepository
from velvet_bot.resilient_ai_quality import ResilientAIQualityRepository
from velvet_bot.resilient_ai_vision import (
    ResilientMediaAIRepository,
    ResilientMediaAIVisionService,
)
from velvet_bot.workers import PeriodicWorkerSpec, WorkerManager
from velvet_bot.workers.iterations import process_backup_once


async def _run_ai_locked(
    lock: asyncio.Lock,
    runner: Callable[[], Awaitable[int]],
) -> int:
    """Do not let two local vision requests compete for the same model memory."""
    async with lock:
        return await runner()


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
        "да",
    }


def _ai_cache_chat_id(settings: Settings) -> int | None:
    if settings.log_chat_id is not None:
        return int(settings.log_chat_id)
    if settings.allowed_user_ids:
        return min(settings.allowed_user_ids)
    return None


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
    if _env_enabled("KRITA_WATERMARK_ENABLED"):
        watermark_service = WatermarkService(
            bot=bot,
            repository=WatermarkRepository(database),
            bridge=KritaBridge(default_krita_bridge_dir()),
        )
        manager.register(
            PeriodicWorkerSpec(
                name="krita-watermark",
                description="Preview и экспорт водяного знака через Krita",
                interval_seconds=2,
                runner=watermark_service.process_once,
            )
        )
    if settings is not None and settings.ai_vision_enabled:
        ai_lock = get_local_ai_lock()
        cache_chat_id = _ai_cache_chat_id(settings)
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
        ai_service.set_cache_chat_id(cache_chat_id)
        quality_service = CalibratedAIQualityService(
            bot=bot,
            repository=ResilientAIQualityRepository(database),
            calibration_repository=QualityCalibrationRepository(database),
            client=QualityVisionClient(
                provider=settings.ai_vision_provider,
                base_url=settings.ai_vision_base_url,
                model=settings.ai_vision_model,
                api_key=settings.ai_vision_api_key,
                timeout_seconds=settings.ai_vision_timeout_seconds,
            ),
            max_attempts=settings.ai_vision_max_attempts,
        )
        quality_service.set_cache_chat_id(cache_chat_id)
        manager.register(
            PeriodicWorkerSpec(
                name="ai-vision",
                description="Смысловой ИИ-анализ изображений",
                interval_seconds=8,
                runner=partial(_run_ai_locked, ai_lock, ai_service.process_once),
            )
        )
        manager.register(
            PeriodicWorkerSpec(
                name="ai-quality",
                description="Qwen-проверка качества изображений",
                interval_seconds=10,
                runner=partial(_run_ai_locked, ai_lock, quality_service.process_once),
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
