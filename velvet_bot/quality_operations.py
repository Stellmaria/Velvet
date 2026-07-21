from __future__ import annotations

from velvet_bot.database import Database


class QualityOperationsRepository:
    """Queue-management operations for the Qwen semantic and quality workers."""

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
        """Return all failed semantic and quality Qwen jobs to their queues."""
        async with self._database.acquire() as connection:
            async with connection.transaction():
                quality_result = await connection.execute(
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
                semantic_result = await connection.execute(
                    """
                    UPDATE media_ai_profiles
                    SET status = 'pending',
                        attempt_count = 0,
                        analysis = '{}'::JSONB,
                        semantic_text = NULL,
                        error_message = NULL,
                        analyzed_at = NULL,
                        updated_at = NOW()
                    WHERE status IN ('error', 'skipped')
                    """
                )
        return _affected_rows(quality_result) + _affected_rows(semantic_result)


def _affected_rows(result: str) -> int:
    try:
        return int(str(result).split()[-1])
    except (TypeError, ValueError, IndexError):
        return 0


__all__ = ("QualityOperationsRepository",)
