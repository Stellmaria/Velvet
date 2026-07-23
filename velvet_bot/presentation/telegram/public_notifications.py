from __future__ import annotations

import asyncio
import logging
from html import escape
from typing import Iterable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.domains.public_archive import PendingPublicNotification, PublicArchiveService

logger = logging.getLogger(__name__)


class PublicNotificationCallback(CallbackData, prefix="pnot"):
    workspace_id: int
    character_id: int
    media_id: int


def notification_keyboard(
    character_id: int,
    media_id: int,
    *,
    workspace_id: int = 1,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Открыть изображение",
                    callback_data=PublicNotificationCallback(
                        workspace_id=int(workspace_id),
                        character_id=int(character_id),
                        media_id=int(media_id),
                    ).pack(),
                )
            ]
        ]
    )


class TelegramPublicNotificationDispatcher:
    """Deliver one workspace notification batch and update delivery state."""

    def __init__(
        self,
        *,
        bot: Bot,
        service: PublicArchiveService,
        workspace_id: int = 1,
    ) -> None:
        self._bot = bot
        self._service = service
        self._workspace_id = int(workspace_id)

    async def deliver(
        self,
        pending: Iterable[PendingPublicNotification],
    ) -> int:
        delivered = 0
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
                        workspace_id=self._workspace_id,
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

    async def process_once(self, *, limit: int = 100) -> int:
        pending = await self._service.list_pending_notifications(limit=limit)
        return await self.deliver(pending)


__all__ = (
    "PublicNotificationCallback",
    "TelegramPublicNotificationDispatcher",
    "notification_keyboard",
)
