from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.public_archive.models import (
    LikeToggleResult,
    PendingPublicNotification,
    PublicMediaState,
)
from velvet_bot.domains.public_archive.visibility import public_media_visibility_sql


class PublicArchiveRepository:
    """PostgreSQL boundary for public likes, subscriptions and notifications."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_media_state(
        self,
        *,
        character_id: int,
        media_id: int,
        user_id: int,
    ) -> PublicMediaState:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM character_media_likes
                        WHERE character_id = $1::BIGINT
                          AND media_id = $2::BIGINT
                    ) AS like_count,
                    EXISTS (
                        SELECT 1
                        FROM character_media_likes
                        WHERE character_id = $1::BIGINT
                          AND media_id = $2::BIGINT
                          AND user_id = $3::BIGINT
                    ) AS liked_by_user,
                    EXISTS (
                        SELECT 1
                        FROM character_subscriptions
                        WHERE character_id = $1::BIGINT
                          AND user_id = $3::BIGINT
                    ) AS subscribed,
                    (
                        SELECT COUNT(*)
                        FROM character_subscriptions
                        WHERE character_id = $1::BIGINT
                    ) AS subscriber_count
                """,
                int(character_id),
                int(media_id),
                int(user_id),
            )
        return PublicMediaState(
            like_count=int(row["like_count"] or 0),
            liked_by_user=bool(row["liked_by_user"]),
            subscribed=bool(row["subscribed"]),
            subscriber_count=int(row["subscriber_count"] or 0),
        )

    async def toggle_like(
        self,
        *,
        character_id: int,
        media_id: int,
        user_id: int,
    ) -> LikeToggleResult:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetchval(
                    """
                    DELETE FROM character_media_likes
                    WHERE character_id = $1::BIGINT
                      AND media_id = $2::BIGINT
                      AND user_id = $3::BIGINT
                    RETURNING 1
                    """,
                    int(character_id),
                    int(media_id),
                    int(user_id),
                )
                liked = deleted is None
                if liked:
                    inserted = await connection.fetchval(
                        """
                        INSERT INTO character_media_likes (
                            character_id,
                            media_id,
                            user_id
                        )
                        VALUES ($1::BIGINT, $2::BIGINT, $3::BIGINT)
                        ON CONFLICT DO NOTHING
                        RETURNING 1
                        """,
                        int(character_id),
                        int(media_id),
                        int(user_id),
                    )
                    liked = inserted is not None
                like_count = int(
                    await connection.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM character_media_likes
                        WHERE character_id = $1::BIGINT
                          AND media_id = $2::BIGINT
                        """,
                        int(character_id),
                        int(media_id),
                    )
                    or 0
                )
        return LikeToggleResult(liked=liked, like_count=like_count)

    async def toggle_subscription(
        self,
        *,
        character_id: int,
        user_id: int,
    ) -> bool:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetchval(
                    """
                    DELETE FROM character_subscriptions
                    WHERE character_id = $1::BIGINT
                      AND user_id = $2::BIGINT
                    RETURNING 1
                    """,
                    int(character_id),
                    int(user_id),
                )
                if deleted is not None:
                    return False
                inserted = await connection.fetchval(
                    """
                    INSERT INTO character_subscriptions (character_id, user_id)
                    VALUES ($1::BIGINT, $2::BIGINT)
                    ON CONFLICT DO NOTHING
                    RETURNING 1
                    """,
                    int(character_id),
                    int(user_id),
                )
                return inserted is not None

    async def list_subscriber_ids(
        self,
        character_id: int,
        *,
        exclude_user_id: int | None = None,
    ) -> list[int]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT user_id
                FROM character_subscriptions
                WHERE character_id = $1::BIGINT
                  AND ($2::BIGINT IS NULL OR user_id <> $2::BIGINT)
                ORDER BY created_at, user_id
                """,
                int(character_id),
                exclude_user_id,
            )
        return [int(row["user_id"]) for row in rows]

    async def remove_subscription(
        self,
        *,
        character_id: int,
        user_id: int,
    ) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                DELETE FROM character_subscriptions
                WHERE character_id = $1::BIGINT
                  AND user_id = $2::BIGINT
                """,
                int(character_id),
                int(user_id),
            )

    async def list_pending_notifications(
        self,
        *,
        limit: int = 100,
    ) -> list[PendingPublicNotification]:
        safe_limit = max(1, min(int(limit), 500))
        visibility_sql = public_media_visibility_sql()
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                f"""
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
                  AND ({visibility_sql})
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

    async def mark_notification_delivered(
        self,
        notification: PendingPublicNotification,
    ) -> bool:
        async with self._database.acquire() as connection:
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


__all__ = ("PublicArchiveRepository",)
