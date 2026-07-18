from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.domains.public_archive import PublicArchiveService
from velvet_bot.public_ui import PublicArchiveCallback

logger = logging.getLogger(__name__)


def notification_keyboard(
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


class TelegramPublicNotificationDispatcher:
    """Deliver public archive notifications and update domain delivery state."""

    def __init__(
        self,
        *,
        bot: Bot,
        service: PublicArchiveService,
    ) -> None:
        self._bot = bot
        self._service = service

    async def process_once(self, *, limit: int = 100) -> int:
        delivered = 0
        pending = await self._service.list_pending_notifications(limit=limit)
        for notification in pending:
            try:
                await self._bot.send_message(
                    chat_id=notification.user_id,
                    text=(
                        "<b>Новое изображение в Velvet Archive</b>\n\n"
                        f"Персонаж: <b>{escape(notification.character_name)}</b>"
                    ),
                    reply_markup=notification_keyboard(
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
                await self._service.remove_subscription(
                    character_id=notification.character_id,
                    user_id=notification.user_id,
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # p2-approved-boundary: isolate-public-notification-delivery
                logger.exception(
                    "Failed to deliver notification to %s for character %s/media %s",
                    notification.user_id,
                    notification.character_id,
                    notification.media_id,
                )
            else:
                await self._service.mark_notification_delivered(notification)
                delivered += 1
        return delivered


__all__ = (
    "TelegramPublicNotificationDispatcher",
    "notification_keyboard",
)
