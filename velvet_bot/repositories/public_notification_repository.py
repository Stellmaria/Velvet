from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.database import Database


@dataclass(frozen=True, slots=True)
class PendingPublicNotification:
    character_id: int
    character_name: str
    media_id: int
    user_id: int


class PublicNotificationRepository:
    """Persistence boundary for public archive subscription deliveries."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def list_pending(self, *, limit: int = 100) -> list[PendingPublicNotification]:
        safe_limit = max(1, min(int(limit), 500))
        async with self.database._require_pool().acquire() as connection:
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
                LIMIT $1::INTEGER
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

    async def mark_delivered(self, notification: PendingPublicNotification) -> bool:
        async with self.database._require_pool().acquire() as connection:
            status = await connection.execute(
                """
                INSERT INTO public_notification_deliveries (
                    character_id,
                    media_id,
                    user_id
                )
                VALUES ($1::BIGINT, $2::BIGINT, $3::BIGINT)
                ON CONFLICT DO NOTHING
                """,
                notification.character_id,
                notification.media_id,
                notification.user_id,
            )
        return status != "INSERT 0 0"
