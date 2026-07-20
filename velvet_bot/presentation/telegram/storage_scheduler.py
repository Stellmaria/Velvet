from __future__ import annotations

import asyncio
import logging
import os

import asyncpg
from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError

from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage import TelegramStorageMigrationService

logger = logging.getLogger(__name__)
_scheduler_task: asyncio.Task[None] | None = None


def _scan_interval_seconds() -> int:
    raw = os.getenv("STORAGE_SCAN_INTERVAL_SECONDS", "3600").strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError("STORAGE_SCAN_INTERVAL_SECONDS должен быть числом.") from error
    if not 300 <= value <= 86400:
        raise ValueError("STORAGE_SCAN_INTERVAL_SECONDS должен быть от 300 до 86400.")
    return value


async def _storage_scheduler_loop(bot: Bot, database: Database) -> None:
    interval = _scan_interval_seconds()
    while True:
        await asyncio.sleep(interval)
        try:
            summary = await TelegramStorageMigrationService(
                bot=bot,
                database=database,
            ).run(migration_kind="resume")
            logger.info(
                "Scheduled Telegram storage scan finished run=%s status=%s "
                "stored=%s deleted=%s freed=%s",
                summary.run_id,
                summary.status,
                summary.stored_files,
                summary.deleted_files,
                summary.freed_bytes,
            )
        except asyncio.CancelledError:
            raise
        except (
            OSError,
            RuntimeError,
            ValueError,
            TelegramAPIError,
            asyncpg.PostgresError,
        ) as error:
            logger.warning("Scheduled Telegram storage scan failed: %s", error)


async def start_storage_scheduler(bot: Bot, database: Database) -> None:
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(
        _storage_scheduler_loop(bot, database),
        name="telegram-storage-recurring-scan",
    )


async def stop_storage_scheduler() -> None:
    global _scheduler_task
    task = _scheduler_task
    _scheduler_task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def register_storage_scheduler(router: Router) -> None:
    router.startup.register(start_storage_scheduler)
    router.shutdown.register(stop_storage_scheduler)


__all__ = ("register_storage_scheduler",)
