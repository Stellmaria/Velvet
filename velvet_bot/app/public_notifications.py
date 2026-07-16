from __future__ import annotations

from aiogram import Bot

from velvet_bot.app.public_archive import build_public_archive_service
from velvet_bot.database import Database
from velvet_bot.presentation.telegram.public_notifications import (
    TelegramPublicNotificationDispatcher,
)


def build_public_notification_dispatcher(
    bot: Bot,
    database: Database,
) -> TelegramPublicNotificationDispatcher:
    return TelegramPublicNotificationDispatcher(
        bot=bot,
        service=build_public_archive_service(database),
    )


__all__ = ("build_public_notification_dispatcher",)
