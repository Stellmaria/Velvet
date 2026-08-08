from __future__ import annotations

import logging

from aiogram import Bot

from velvet_bot.backup_runtime import BackupService
from velvet_bot.core.config import Settings
from velvet_bot.core.config.kie import KieSettings
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import AITaskQueueService, AIUsageService
from velvet_bot.error_center import ErrorIncidentCenter
from velvet_bot.services.codex_recovery_notifications import (
    build_codex_recovery_notification_monitor,
)
from velvet_bot.services.diagnostic_bundle import DiagnosticBundleService
from velvet_bot.services.system_health import SystemHealthService
from velvet_bot.workers import PeriodicWorkerSpec, WorkerManager

_INSTALLED = False
_FINALIZED = False
_WORKER_NAME = "codex-recovery-notifications"
logger = logging.getLogger(__name__)


def _owner_chat_id(settings: Settings) -> int | None:
    if settings.allowed_user_ids:
        return min(settings.allowed_user_ids)
    if settings.log_chat_id is not None:
        return int(settings.log_chat_id)
    return None


def _finalize_worker_builder() -> None:
    """Attach the recovery monitor to the fully composed main-bot worker builder."""
    global _FINALIZED
    if _FINALIZED:
        return

    from velvet_bot.app import bootstrap
    from velvet_bot.app import workers as workers_module

    original = workers_module.build_worker_manager

    def build_worker_manager_with_codex_recovery(
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
        manager = original(
            bot=bot,
            database=database,
            backup_service=backup_service,
            settings=settings,
            ai_usage_service=ai_usage_service,
            ai_task_queue_service=ai_task_queue_service,
            kie_settings=kie_settings,
            error_center=error_center,
            system_service=system_service,
            diagnostic_service=diagnostic_service,
        )
        if settings is None or _WORKER_NAME in manager.registered_names():
            return manager

        async def send_notification(chat_id: int, text: str) -> None:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                disable_web_page_preview=True,
            )

        monitor = build_codex_recovery_notification_monitor(
            send_notification=send_notification,
            owner_chat_id=_owner_chat_id(settings),
        )
        if monitor is None:
            return manager
        manager.register(
            PeriodicWorkerSpec(
                name=_WORKER_NAME,
                description="Уведомление владельцу о восстановлении Codex quota",
                interval_seconds=60,
                runner=monitor.process_once,
            )
        )
        logger.info("Installed Codex recovery notification worker name=%s", _WORKER_NAME)
        return manager

    workers_module.build_worker_manager = build_worker_manager_with_codex_recovery
    bootstrap.build_worker_manager = build_worker_manager_with_codex_recovery
    _FINALIZED = True


def install_codex_recovery_bootstrap() -> None:
    """Finalize recovery notification wiring immediately before app startup."""
    global _INSTALLED
    if _INSTALLED:
        return

    from velvet_bot.app import bootstrap

    original_run_application = bootstrap.run_application

    async def run_application_with_codex_recovery() -> None:
        _finalize_worker_builder()
        await original_run_application()

    bootstrap.run_application = run_application_with_codex_recovery
    _INSTALLED = True


__all__ = ("install_codex_recovery_bootstrap",)
