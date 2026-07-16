from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.database import Database
from velvet_bot.public_catalog import remove_character_subscription
from velvet_bot.public_ui import PublicArchiveCallback
from velvet_bot.repositories.public_notification_repository import (
    PendingPublicNotification,
    PublicNotificationRepository,
)

logger = logging.getLogger(__name__)


def _notification_keyboard(
    character_id: int,
    media_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Открыть новое изображение",
                    callback_data=PublicArchiveCallback(
                        action="open",
                        character_id=character_id,
                        offset=0,
                        media_id=media_id,
                        page=0,
                    ).pack(),
                )
            ]
        ]
    )


async def _list_pending_notifications(
    database: Database,
    *,
    limit: int = 100,
) -> list[PendingPublicNotification]:
    """Backward-compatible wrapper around PublicNotificationRepository."""
    return await PublicNotificationRepository(database).list_pending(limit=limit)


async def _mark_delivered(
    database: Database,
    notification: PendingPublicNotification,
) -> None:
    """Backward-compatible delivery marker wrapper."""
    await PublicNotificationRepository(database).mark_delivered(notification)


async def process_public_notifications_once(
    bot: Bot,
    database: Database,
    *,
    limit: int = 100,
) -> int:
    """Deliver one bounded notification batch and return successful deliveries."""
    repository = PublicNotificationRepository(database)
    delivered = 0
    pending = await repository.list_pending(limit=limit)
    for notification in pending:
        try:
            await bot.send_message(
                chat_id=notification.user_id,
                text=(
                    "<b>Новое изображение в Velvet Archive</b>\n\n"
                    f"Персонаж: <b>{escape(notification.character_name)}</b>"
                ),
                reply_markup=_notification_keyboard(
                    notification.character_id,
                    notification.media_id,
                ),
            )
        except (TelegramForbiddenError, TelegramBadRequest) as error:
            logger.info(
                "Removing unreachable subscriber %s for character %s: %s",
                notification.user_id,
                notification.character_id,
                error,
            )
            await remove_character_subscription(
                database,
                character_id=notification.character_id,
                user_id=notification.user_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Failed to deliver notification to %s for character %s/media %s",
                notification.user_id,
                notification.character_id,
                notification.media_id,
            )
        else:
            await repository.mark_delivered(notification)
            delivered += 1
    return delivered


async def run_public_notification_worker(
    bot: Bot,
    database: Database,
    *,
    interval_seconds: float = 5.0,
) -> None:
    """Backward-compatible standalone loop for public notifications."""
    while True:
        try:
            await process_public_notifications_once(bot, database)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Public notification worker iteration failed")
        await asyncio.sleep(max(1.0, interval_seconds))


__all__ = (
    "PendingPublicNotification",
    "process_public_notifications_once",
    "run_public_notification_worker",
)
