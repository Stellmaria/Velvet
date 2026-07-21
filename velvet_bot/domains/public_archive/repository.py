from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.public_archive.models import (
    LikeToggleResult,
    PendingPublicNotification,
    PUBLIC_ARCHIVE_REVIEWER_ID,
    PublicDownloadSource,
    PublicMediaState,
)
from velvet_bot.domains.public_archive.visibility import public_media_visibility_sql


class PublicArchiveRepository:
    """PostgreSQL boundary for public likes, subscriptions and media activity."""

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
                    ) AS subscriber_count,
                    COALESCE((
                        SELECT SUM(view_count)
                        FROM public_media_view_stats
                        WHERE character_id = $1::BIGINT
                          AND media_id = $2::BIGINT
                    ), 0) AS view_count,
                    COALESCE((
                        SELECT SUM(download_count)
                        FROM public_media_download_stats
                        WHERE character_id = $1::BIGINT
                          AND media_id = $2::BIGINT
                    ), 0) AS download_count,
                    EXISTS (
                        SELECT 1
                        FROM public_media_view_stats
                        WHERE character_id = $1::BIGINT
                          AND media_id = $2::BIGINT
                          AND user_id = $4::BIGINT
                    ) AS reviewed_by_owner,
                    COALESCE((
                        SELECT watermark_applied
                        FROM media_files
                        WHERE id = $2::BIGINT
                    ), FALSE) AS watermark_applied,
                    COALESCE((
                        SELECT watermark_approved
                        FROM media_files
                        WHERE id = $2::BIGINT
                    ), FALSE) AS watermark_approved
                """,
                int(character_id),
                int(media_id),
                int(user_id),
                PUBLIC_ARCHIVE_REVIEWER_ID,
            )
        return PublicMediaState(
            like_count=int(row["like_count"] or 0),
            liked_by_user=bool(row["liked_by_user"]),
            subscribed=bool(row["subscribed"]),
            subscriber_count=int(row["subscriber_count"] or 0),
            view_count=int(row["view_count"] or 0),
            download_count=int(row["download_count"] or 0),
            reviewed_by_owner=bool(row["reviewed_by_owner"]),
            watermark_applied=bool(row["watermark_applied"]),
            watermark_approved=bool(row["watermark_approved"]),
        )

    async def record_view(
        self,
        *,
        character_id: int,
        media_id: int,
        user_id: int,
    ) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO public_media_view_stats (
                    character_id,
                    media_id,
                    user_id,
                    view_count
                )
                VALUES ($1::BIGINT, $2::BIGINT, $3::BIGINT, 1)
                ON CONFLICT (character_id, media_id, user_id)
                DO UPDATE SET
                    view_count = public_media_view_stats.view_count + 1,
                    last_viewed_at = NOW()
                """,
                int(character_id),
                int(media_id),
                int(user_id),
            )

    async def resolve_download_source(
        self,
        *,
        character_id: int,
        media_id: int,
        member_access: bool,
    ) -> PublicDownloadSource | None:
        visibility_sql = public_media_visibility_sql(
            include_adult_restricted=True,
            include_oversized_images=True,
        )
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                SELECT
                    mf.telegram_file_id,
                    mf.source_telegram_file_id,
                    mf.watermark_applied,
                    mf.watermark_approved
                FROM character_media AS cm
                JOIN media_files AS mf ON mf.id = cm.media_id
                WHERE cm.character_id = $1::BIGINT
                  AND cm.media_id = $2::BIGINT
                  AND ({visibility_sql})
                """,
                int(character_id),
                int(media_id),
            )
        if row is None:
            return None
        if member_access:
            return PublicDownloadSource(
                telegram_file_id=str(
                    row["source_telegram_file_id"] or row["telegram_file_id"]
                ),
                variant="original",
            )
        if bool(row["watermark_applied"]) and bool(row["watermark_approved"]):
            return PublicDownloadSource(
                telegram_file_id=str(row["telegram_file_id"]),
                variant="watermarked",
            )
        return None

    async def record_download(
        self,
        *,
        character_id: int,
        media_id: int,
        user_id: int,
        variant: str,
    ) -> None:
        if variant not in {"original", "watermarked"}:
            raise ValueError("Неизвестный вариант скачивания.")
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO public_media_download_stats (
                    character_id,
                    media_id,
                    user_id,
                    download_count,
                    last_variant
                )
                VALUES ($1::BIGINT, $2::BIGINT, $3::BIGINT, 1, $4::VARCHAR)
                ON CONFLICT (character_id, media_id, user_id)
                DO UPDATE SET
                    download_count = public_media_download_stats.download_count + 1,
                    last_variant = EXCLUDED.last_variant,
                    last_downloaded_at = NOW()
                """,
                int(character_id),
                int(media_id),
                int(user_id),
                variant,
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
