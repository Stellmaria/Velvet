from __future__ import annotations

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from velvet_bot.database import Character, Database
from velvet_bot.public_catalog import (
    list_character_subscriber_ids,
    remove_character_subscription,
)
from velvet_bot.public_ui import build_public_notification_keyboard

logger = logging.getLogger(__name__)


async def notify_character_subscribers(
    bot: Bot,
    database: Database,
    character: Character,
    *,
    media_id: int,
    exclude_user_id: int | None = None,
) -> int:
    """Notify subscribers after a new archive link is created.

    Delivery failures caused by a blocked or unavailable private chat remove the stale
    subscription, so one unreachable user does not poison every future notification.
    """
    subscriber_ids = await list_character_subscriber_ids(
        database,
        character.id,
        exclude_user_id=exclude_user_id,
    )
    delivered = 0
    for user_id in subscriber_ids:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    "<b>Новый материал в Velvet Archive</b>\n\n"
                    f"Персонаж: <b>{escape(character.name)}</b>"
                ),
                reply_markup=build_public_notification_keyboard(character.id),
                disable_notification=False,
            )
            delivered += 1
        except (TelegramForbiddenError, TelegramBadRequest) as error:
            logger.info(
                "Removing unreachable public archive subscriber %s for character %s: %s",
                user_id,
                character.id,
                error,
            )
            await remove_character_subscription(
                database,
                character_id=character.id,
                user_id=user_id,
            )
        except Exception:
            logger.exception(
                "Failed to notify subscriber %s for character %s and media %s",
                user_id,
                character.id,
                media_id,
            )
    return delivered
