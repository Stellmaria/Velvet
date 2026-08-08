from __future__ import annotations

import logging

from aiogram import Bot

from velvet_bot.core.config import Settings, load_settings
from velvet_bot.services.codex_recovery_notifications import (
    build_codex_recovery_notification_monitor,
)
from velvet_bot.workers import PeriodicWorkerSpec, WorkerManager

_WORKER_NAME = "codex-recovery-notifications"
logger = logging.getLogger(__name__)


def _owner_chat_id(settings: Settings) -> int | None:
    if settings.allowed_user_ids:
        return min(settings.allowed_user_ids)
    if settings.log_chat_id is not None:
        return int(settings.log_chat_id)
    return None


def register_codex_recovery_worker(
    *,
    bot: Bot,
    manager: WorkerManager,
    settings: Settings | None = None,
) -> None:
    if _WORKER_NAME in manager.registered_names():
        return

    resolved_settings = settings or load_settings()

    async def send_notification(chat_id: int, text: str) -> None:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            disable_web_page_preview=True,
        )

    monitor = build_codex_recovery_notification_monitor(
        send_notification=send_notification,
        owner_chat_id=_owner_chat_id(resolved_settings),
    )
    if monitor is None:
        return
    manager.register(
        PeriodicWorkerSpec(
            name=_WORKER_NAME,
            description="Уведомление владельцу о восстановлении Codex quota",
            interval_seconds=60,
            runner=monitor.process_once,
        )
    )
    logger.info("Registered Codex recovery notification worker name=%s", _WORKER_NAME)


__all__ = ("register_codex_recovery_worker",)
