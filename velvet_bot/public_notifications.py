from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.database import Database
from velvet_bot.public_catalog import remove_character_subscription
from velvet_bot.public_ui import PublicArchiveCallback

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PendingPublicNotification:
    character_id: int
    character_name: str
    media_id: int
    user_id: int


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
    safe_limit = max(1, min(limit, 500))
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                cs.character_id,
                c.name AS character_name,
                cm.media_id,
                cs.user_id
            FROM character_subscriptions AS cs
            JOIN characters AS c ON c.id = cs.character_id
            JOIN character_media AS cm
              ON cm.character_id = cs.character_id
             AND cm.created_at > cs.created_at
            JOIN media_files AS mf ON mf.id = cm.media_id
            LEFT JOIN public_notification_deliveries AS pnd
              ON pnd.character_id = cs.character_id
             AND pnd.media_id = cm.media_id
             AND pnd.user_id = cs.user_id
            WHERE pnd.user_id IS NULL
              AND (
                    mf.media_type = 'photo'
                    OR COALESCE(mf.mime_type, '') LIKE 'image/%'
                  )
            ORDER BY cm.created_at, cs.created_at, cs.user_id
            LIMIT $1
            """,
            safe_limit,
        )
    return [
        PendingPublicNotification(
            character_id=int(row["character_id"]),
            character_name=str(row["character_name"]),
            media_id=int(row["media_id"]),
            user_id=int(row["user_id"]),
        )
        for row in rows
    ]


async def _mark_delivered(
    database: Database,
    notification: PendingPublicNotification,
) -> None:
    async with database._require_pool().acquire() as connection:
        await connection.execute(
            """
            INSERT INTO public_notification_deliveries (
                character_id,
                media_id,
                user_id
            )
            VALUES ($1, $2, $3)
            ON CONFLICT DO NOTHING
            """,
            notification.character_id,
            notification.media_id,
            notification.user_id,
        )


async def run_public_notification_worker(
    bot: Bot,
    database: Database,
    *,
    interval_seconds: float = 5.0,
) -> None:
    """Deliver notifications for images added after each user's subscription time."""
    while True:
        try:
            pending = await _list_pending_notifications(database)
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
                    await _mark_delivered(database, notification)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Public notification worker iteration failed")

        await asyncio.sleep(max(1.0, interval_seconds))
