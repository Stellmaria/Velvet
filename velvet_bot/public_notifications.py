from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from velvet_bot.app.public_archive import build_public_archive_service
from velvet_bot.app.public_notifications import build_public_notification_dispatcher
from velvet_bot.database import Database
from velvet_bot.domains.public_archive import PendingPublicNotification
from velvet_bot.presentation.telegram.public_notifications import notification_keyboard

logger = logging.getLogger(__name__)
_notification_keyboard = notification_keyboard


async def _list_pending_notifications(
    database: Database,
    *,
    limit: int = 100,
) -> list[PendingPublicNotification]:
    return await build_public_archive_service(database).list_pending_notifications(
        limit=limit
    )


async def _mark_delivered(
    database: Database,
    notification: PendingPublicNotification,
) -> None:
    await build_public_archive_service(database).mark_notification_delivered(
        notification
    )


async def process_public_notifications_once(
    bot: Bot,
    database: Database,
    *,
    limit: int = 100,
) -> int:
    return await build_public_notification_dispatcher(bot, database).process_once(
        limit=limit
    )


async def run_public_notification_worker(
    bot: Bot,
    database: Database,
    *,
    interval_seconds: float = 5.0,
) -> None:
    dispatcher = build_public_notification_dispatcher(bot, database)
    while True:
        try:
            await dispatcher.process_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # p2-approved-boundary: isolate-public-notification-worker-iteration
            logger.exception("Public notification worker iteration failed")
        await asyncio.sleep(max(1.0, interval_seconds))


__all__ = (
    "PendingPublicNotification",
    "process_public_notifications_once",
    "run_public_notification_worker",
)
