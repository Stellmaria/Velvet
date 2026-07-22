from __future__ import annotations

from velvet_bot.database import Database

_ACTIVE_STATUSES = ("needs_fix", "checking", "ready_for_review")


async def request_manual_rework(
    database: Database,
    *,
    media_id: int,
    user_id: int,
    reason: str = "Стэл отправила работу на доработку из публичного архива.",
) -> bool:
    """Create or reopen one admin rework item without duplicating active requests."""

    async with database.acquire() as connection:
        async with connection.transaction():
            existing = await connection.fetchrow(
                """
                SELECT status, source
                FROM media_rework_items
                WHERE media_id = $1::BIGINT
                FOR UPDATE
                """,
                int(media_id),
            )
            await connection.execute(
                """
                UPDATE character_media
                SET is_public = FALSE
                WHERE media_id = $1::BIGINT
                """,
                int(media_id),
            )
            if (
                existing is not None
                and str(existing["status"]) in _ACTIVE_STATUSES
                and str(existing["source"]) in {"admin", "mixed"}
            ):
                return False

            if existing is None:
                await connection.execute(
                    """
                    INSERT INTO media_rework_items (
                        media_id,
                        status,
                        source,
                        reason,
                        requested_by,
                        last_action_by,
                        updated_at
                    )
                    VALUES (
                        $1::BIGINT,
                        'needs_fix',
                        'admin',
                        $3::TEXT,
                        $2::BIGINT,
                        $2::BIGINT,
                        NOW()
                    )
                    """,
                    int(media_id),
                    int(user_id),
                    reason,
                )
            else:
                source = "admin" if str(existing["source"]) == "admin" else "mixed"
                await connection.execute(
                    """
                    UPDATE media_rework_items
                    SET status = 'needs_fix',
                        source = $3::VARCHAR,
                        reason = $4::TEXT,
                        requested_by = $2::BIGINT,
                        last_action_by = $2::BIGINT,
                        resolved_at = NULL,
                        updated_at = NOW()
                    WHERE media_id = $1::BIGINT
                    """,
                    int(media_id),
                    int(user_id),
                    source,
                    reason,
                )

            await connection.execute(
                """
                INSERT INTO media_rework_events (
                    media_id,
                    action,
                    source,
                    actor_user_id,
                    reason
                )
                VALUES (
                    $1::BIGINT,
                    'admin_flagged',
                    'admin',
                    $2::BIGINT,
                    $3::TEXT
                )
                """,
                int(media_id),
                int(user_id),
                reason,
            )
    return True


__all__ = ("request_manual_rework",)
