from __future__ import annotations

import asyncio
import os
from functools import partial
from typing import Awaitable, Callable

from aiogram import Bot

from velvet_bot.ai_quality import (
    QualityVisionClient,
    build_quality_vision_contract,
)
from velvet_bot.app.ai_vision_logging import run_ai_vision_once_with_terminal_skip_info
from velvet_bot.app.public_notifications import build_public_notification_dispatcher
from velvet_bot.app.publication import build_publication_service
from velvet_bot.backup_runtime import BackupService
from velvet_bot.calibrated_ai_quality import CalibratedAIQualityService
from velvet_bot.core.config import Settings
from velvet_bot.core.config.kie import KieSettings, load_kie_settings
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import (
    AIRequestExecutor,
    AITaskQueueService,
    AIUsageService,
    build_ai_task_queue_service,
    build_ai_usage_service,
)
from velvet_bot.domains.media_generation.friendly_worker import (
    FriendlyKieGenerationWorker as KieGenerationWorker,
)
from velvet_bot.domains.media_generation.task_queue import KieTaskQueueService
from velvet_bot.domains.media_quality import MediaQualityRepository, MediaQualityService
from velvet_bot.domains.vision_batches import build_vision_batch_consumer
from velvet_bot.domains.vision_routing import build_vision_cascade_router
from velvet_bot.domains.vision_routing.integration import (
    CascadeMediaAIRepository,
    CascadeMediaAIVisionService,
    VisionCascadeAdapter,
)
from velvet_bot.domains.watermark.repository import WatermarkRepository
from velvet_bot.domains.watermark.service import WatermarkService
from velvet_bot.domains.workspaces.qwen_repository import WorkspaceQwenRepository
from velvet_bot.error_center import ErrorIncidentCenter
from velvet_bot.infrastructure.ai import KieClient
from velvet_bot.infrastructure.krita_bridge import KritaBridge, default_krita_bridge_dir
from velvet_bot.infrastructure.postgres.ai_task_wakeup_repository import PostgresAITaskListener
from velvet_bot.infrastructure.transient_connections import (
    install_recoverable_polling_filter,
    recover_database_pool,
)
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.quality_calibration import QualityCalibrationRepository
from velvet_bot.resilient_ai_quality import ResilientAIQualityRepository
from velvet_bot.services.diagnostic_bundle import DiagnosticBundleService
from velvet_bot.services.system_health import SystemHealthService
from velvet_bot.services.workspace_qwen_quality import WorkspaceQwenQualityService
from velvet_bot.workers import PeriodicWorkerSpec, WorkerManager
from velvet_bot.workers.adaptive import AdaptiveQueueWait
from velvet_bot.workers.iterations import process_backup_once


async def _run_ai_locked(
    lock: asyncio.Lock,
    runner: Callable[[], Awaitable[int]],
) -> int:
    """Do not let two local vision requests compete for the same model memory."""
    async with lock:
        return await runner()


async def _recover_stale_ai_tasks(service: AITaskQueueService) -> int:
    recovered = await service.recover_expired_locks(
        stale_after_seconds=900,
        limit=100,
    )
    return len(recovered)


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
    ai_usage_service: AIUsageService | None = None,
    ai_task_queue_service: AITaskQueueService | None = None,
    kie_settings: KieSettings | None = None,
    error_center: ErrorIncidentCenter | None = None,
    system_service: SystemHealthService | None = None,
    diagnostic_service: DiagnosticBundleService | None = None,
) -> WorkerManager:
    """Build the complete periodic-worker registry for the application."""
    public_notifications = build_public_notification_dispatcher(bot, database)
    publication_service = build_publication_service(bot, database)
    media_quality_service = MediaQualityService(
        bot=bot,
        repository=MediaQualityRepository(database),
    )
    active_task_queue_service = (
        ai_task_queue_service or build_ai_task_queue_service(database=database)
    )
    active_kie_settings = kie_settings or load_kie_settings()
    active_usage_service = ai_usage_service

    manager = WorkerManager(
        transient_failure_handler=partial(recover_database_pool, database),
    )
    if error_center is not None:
        install_recoverable_polling_filter(error_center)
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
            name="ai-task-stale-recovery",
            description="Восстановление зависших AI-задач",
            interval_seconds=300,
            runner=partial(_recover_stale_ai_tasks, active_task_queue_service),
        )
    )
    if active_kie_settings.enabled:
        if active_kie_settings.api_key is None:
            raise RuntimeError("Kie включён без API key.")
        if active_usage_service is None:
            active_usage_service = build_ai_usage_service(database=database)
        kie_client = KieClient(
            api_key=(active_kie_settings.api_key),
            models=active_kie_settings.models,
            base_url=active_kie_settings.base_url,
            file_upload_base_url=active_kie_settings.file_upload_base_url,
            timeout_seconds=active_kie_settings.timeout_seconds,
            poll_interval_seconds=min(active_kie_settings.poll_interval_seconds, 2),
            task_timeout_seconds=active_kie_settings.task_timeout_seconds,
            grs_api_key=active_kie_settings.grs_api_key,
            grs_base_url=active_kie_settings.grs_base_url,
        )
        kie_queue = KieTaskQueueService(
            database=database,
            max_attempts=active_kie_settings.generation_max_attempts,
        )
        for slot in range(1, active_kie_settings.max_concurrent_generations + 1):
            worker_name = (
                "kie-media-generation"
                if slot == 1
                else f"kie-media-generation-{slot}"
            )
            kie_worker = KieGenerationWorker(
                bot=bot,
                queue=kie_queue,
                client=kie_client,
                executor=AIRequestExecutor(active_usage_service),
                pricing=active_kie_settings.pricing,
                usd_to_rub=active_kie_settings.usd_to_rub,
                worker_id=worker_name,
            )
            manager.register(
                PeriodicWorkerSpec(
                    name=worker_name,
                    description=(
                        "Экономная генерация фото и видео через Ауф "
                        f"· слот {slot}/{active_kie_settings.max_concurrent_generations}"
                    ),
                    interval_seconds=1,
                    runner=kie_worker.process_once,
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
        if active_usage_service is None:
            active_usage_service = build_ai_usage_service(database=database)
        vision_router = build_vision_cascade_router(
            settings=settings,
            database=database,
            ai_usage_service=active_usage_service,
        )
        ai_service = CascadeMediaAIVisionService(
            bot=bot,
            repository=CascadeMediaAIRepository(database),
            client=VisionCascadeAdapter(vision_router),
            max_attempts=settings.ai_vision_max_attempts,
        )
        ai_service.set_cache_chat_id(cache_chat_id)
        quality_service: CalibratedAIQualityService | None = None
        if _env_enabled("AI_QUALITY_ENABLED"):
            quality_service = CalibratedAIQualityService(
                bot=bot,
                repository=ResilientAIQualityRepository(database),
                calibration_repository=QualityCalibrationRepository(database),
                client=QualityVisionClient(
                    provider=settings.ai_vision_provider,
                    base_url=settings.ai_vision_base_url,
                    model=settings.ai_vision_model,
                    api_key=(settings.ai_vision_api_key),
                    timeout_seconds=settings.ai_vision_timeout_seconds,
                ),
                max_attempts=settings.ai_vision_max_attempts,
            )
            quality_service.set_cache_chat_id(cache_chat_id)
        workspace_quality_router = build_vision_cascade_router(
            settings=settings,
            database=database,
            ai_usage_service=active_usage_service,
            contract=build_quality_vision_contract(),
            analysis_type="personal-quality",
            prompt_version=1,
            include_sensitive=False,
        )
        workspace_quality_service = WorkspaceQwenQualityService(
            bot=bot,
            repository=WorkspaceQwenRepository(database),
            client=workspace_quality_router,
            max_attempts=settings.ai_vision_max_attempts,
        )
        if _env_enabled("AI_VISION_QUEUE_ENABLED"):
            batch_consumer = build_vision_batch_consumer(
                bot=bot,
                database=database,
                settings=settings,
                usage_service=active_usage_service,
                queue_service=active_task_queue_service,
                cache_chat_id=cache_chat_id,
            )
            manager.register(
                PeriodicWorkerSpec(
                    name="ai-vision-queue",
                    description="Пакетная очередь смыслового VL-анализа",
                    interval_seconds=3,
                    runner=batch_consumer.process_once,
                    wait_controller=AdaptiveQueueWait(
                        PostgresAITaskListener(database.database_url),
                    ),
                )
            )
        else:
            manager.register(
                PeriodicWorkerSpec(
                    name="ai-vision",
                    description="Каскадный смысловой VL-анализ изображений",
                    interval_seconds=8,
                    runner=partial(
                        _run_ai_locked,
                        ai_lock,
                        partial(
                            run_ai_vision_once_with_terminal_skip_info,
                            ai_service.process_once,
                        ),
                    ),
                )
            )
        if quality_service is not None:
            manager.register(
                PeriodicWorkerSpec(
                    name="ai-quality",
                    description="Qwen-проверка качества изображений",
                    interval_seconds=10,
                    runner=partial(_run_ai_locked, ai_lock, quality_service.process_once),
                )
            )
        manager.register(
            PeriodicWorkerSpec(
                name="workspace-qwen-quality",
                description="Provider-neutral проверка личных пространств",
                interval_seconds=11,
                runner=partial(
                    _run_ai_locked,
                    ai_lock,
                    workspace_quality_service.process_once,
                ),
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
    if diagnostic_service is not None and system_service is not None:
        manager.register(
            PeriodicWorkerSpec(
                name="owner-diagnostics",
                description="Критическая диагностика и ZIP владельцу",
                interval_seconds=300,
                runner=partial(
                    diagnostic_service.monitor_once,
                    bot=bot,
                    system_service=system_service,
                    worker_manager=manager,
                ),
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
