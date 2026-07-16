from __future__ import annotations

import json

from velvet_bot.database import Database


class PublicationRepository:
    """Persistence boundary for publication status transitions and queue claims."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def claim_for_publishing(self, draft_id: int) -> bool:
        async with self.database._require_pool().acquire() as connection:
            status = await connection.execute(
                """
                UPDATE publication_drafts
                SET status = 'publishing',
                    attempt_count = attempt_count + 1,
                    last_error = NULL,
                    updated_at = NOW()
                WHERE id = $1::BIGINT
                  AND status IN ('draft', 'checked', 'scheduled', 'error')
                """,
                int(draft_id),
            )
        return status != "UPDATE 0"

    async def mark_published(
        self,
        draft_id: int,
        *,
        message_ids: list[int],
        actor_id: int | None,
    ) -> None:
        details = json.dumps({"message_ids": message_ids}, ensure_ascii=False)
        async with self.database._require_pool().acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE publication_drafts
                    SET status = 'published',
                        published_at = NOW(),
                        published_message_ids = $2::BIGINT[],
                        scheduled_at = NULL,
                        last_error = NULL,
                        updated_at = NOW()
                    WHERE id = $1::BIGINT
                    """,
                    int(draft_id),
                    [int(value) for value in message_ids],
                )
                await connection.execute(
                    """
                    INSERT INTO publication_events (
                        draft_id, event_type, actor_id, details
                    )
                    VALUES ($1::BIGINT, 'published', $2::BIGINT, $3::JSONB)
                    """,
                    int(draft_id),
                    actor_id,
                    details,
                )

    async def mark_error(
        self,
        draft_id: int,
        *,
        error: Exception | str,
        actor_id: int | None,
    ) -> None:
        message = str(error)[:4000]
        details = json.dumps({"error": message}, ensure_ascii=False)
        async with self.database._require_pool().acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE publication_drafts
                    SET status = 'error',
                        last_error = $2::TEXT,
                        updated_at = NOW()
                    WHERE id = $1::BIGINT
                    """,
                    int(draft_id),
                    message,
                )
                await connection.execute(
                    """
                    INSERT INTO publication_events (
                        draft_id, event_type, actor_id, details
                    )
                    VALUES ($1::BIGINT, 'error', $2::BIGINT, $3::JSONB)
                    """,
                    int(draft_id),
                    actor_id,
                    details,
                )

    async def list_due_draft_ids(self, *, limit: int = 5) -> list[int]:
        safe_limit = max(1, min(int(limit), 20))
        async with self.database._require_pool().acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE publication_drafts
                    SET status = 'error',
                        last_error = COALESCE(
                            last_error,
                            'Публикация зависла и была остановлена.'
                        ),
                        updated_at = NOW()
                    WHERE status = 'publishing'
                      AND updated_at < NOW() - INTERVAL '15 minutes'
                    """
                )
                rows = await connection.fetch(
                    """
                    SELECT id
                    FROM publication_drafts
                    WHERE status = 'scheduled'
                      AND scheduled_at <= NOW()
                    ORDER BY scheduled_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT $1::INTEGER
                    """,
                    safe_limit,
                )
        return [int(row["id"]) for row in rows]
