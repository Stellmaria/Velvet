from __future__ import annotations

from velvet_bot.database import Database


class QualityOperationsRepository:
    """Queue-management operations for the Qwen quality worker."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def enqueue_recent(self, *, limit: int = 24) -> int:
        """Queue recent unanalysed images and reset recent failed checks."""
        safe_limit = max(1, min(int(limit), 100))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                WITH recent AS (
                    SELECT id
                    FROM media_files
                    WHERE media_type = 'photo'
                       OR (
                            media_type = 'document'
                            AND COALESCE(mime_type, '') LIKE 'image/%'
                       )
                    ORDER BY id DESC
                    LIMIT $1::INTEGER
                )
                INSERT INTO media_ai_quality_checks AS quality (
                    media_id,
                    status,
                    attempt_count,
                    updated_at
                )
                SELECT id, 'pending', 0, NOW()
                FROM recent
                ON CONFLICT (media_id) DO UPDATE
                SET status = 'pending',
                    attempt_count = 0,
                    verdict = NULL,
                    quality_score = NULL,
                    confidence = NULL,
                    report = NULL,
                    decision = NULL,
                    decided_by = NULL,
                    decided_at = NULL,
                    error_message = NULL,
                    analyzed_at = NULL,
                    updated_at = NOW()
                WHERE quality.status IN ('error', 'skipped')
                RETURNING media_id
                """,
                safe_limit,
            )
        return len(rows)

    async def retry_errors(self) -> int:
        """Return all failed or permanently skipped quality checks to the queue."""
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE media_ai_quality_checks
                SET status = 'pending',
                    attempt_count = 0,
                    verdict = NULL,
                    quality_score = NULL,
                    confidence = NULL,
                    report = NULL,
                    decision = NULL,
                    decided_by = NULL,
                    decided_at = NULL,
                    error_message = NULL,
                    analyzed_at = NULL,
                    updated_at = NOW()
                WHERE status IN ('error', 'skipped')
                """
            )
        return int(result.split()[-1])


__all__ = ("QualityOperationsRepository",)
