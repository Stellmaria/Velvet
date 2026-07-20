from __future__ import annotations

from velvet_bot.ai_quality import AIQualityRepository
from velvet_bot.ai_vision import VisionAnalysisTarget
from velvet_bot.database import Database

_QUALITY_RESPONSE_VERSION = 2


class ResilientAIQualityRepository(AIQualityRepository):
    """Requeue quality checks skipped before oversized preview recovery existed."""

    def __init__(self, database: Database) -> None:
        super().__init__(database)

    async def claim_targets(
        self,
        *,
        provider: str,
        model: str,
        max_attempts: int,
        limit: int = 1,
    ) -> tuple[VisionAnalysisTarget, ...]:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE media_ai_quality_checks
                SET status = 'pending',
                    attempt_count = 0,
                    error_message = NULL,
                    analyzed_at = NULL,
                    updated_at = NOW()
                WHERE analysis_version < $1::SMALLINT
                  AND status IN ('error', 'skipped')
                  AND LOWER(error_message) LIKE '%file is too big%'
                """,
                _QUALITY_RESPONSE_VERSION,
            )

        targets = await super().claim_targets(
            provider=provider,
            model=model,
            max_attempts=max_attempts,
            limit=limit,
        )
        if targets:
            async with self._database.acquire() as connection:
                await connection.execute(
                    """
                    UPDATE media_ai_quality_checks
                    SET analysis_version = $2::SMALLINT,
                        updated_at = NOW()
                    WHERE media_id = ANY($1::BIGINT[])
                    """,
                    [target.media_id for target in targets],
                    _QUALITY_RESPONSE_VERSION,
                )
        return targets

    async def save_preview_file_id(self, media_id: int, preview_file_id: str) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE media_files
                SET preview_file_id = $2::TEXT
                WHERE id = $1::BIGINT
                  AND preview_file_id IS DISTINCT FROM $2::TEXT
                """,
                int(media_id),
                str(preview_file_id),
            )


__all__ = ("ResilientAIQualityRepository",)
