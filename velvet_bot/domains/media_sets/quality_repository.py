from __future__ import annotations

from velvet_bot.database import Database


async def _retire_weak_fallback_candidates(database: Database) -> None:
    """Hide filename/time guesses once the archive is queued for AI analysis."""
    async with database.acquire() as connection:
        await connection.execute(
            """
            UPDATE media_set_candidates
            SET status = 'ignored',
                decided_at = COALESCE(decided_at, NOW()),
                updated_at = NOW(),
                reason = CASE
                    WHEN reason LIKE '%Скрыто после включения Qwen.%'
                        THEN reason
                    ELSE reason || ' Скрыто после включения Qwen.'
                END
            WHERE status = 'pending'
              AND (
                    candidate_key LIKE 'filename:%'
                    OR candidate_key LIKE 'context:%'
                  )
            """
        )


async def _latest_ai_error(database: Database) -> str | None:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT error_message
            FROM media_ai_profiles
            WHERE status IN ('error', 'skipped')
              AND NULLIF(BTRIM(error_message), '') IS NOT NULL
            ORDER BY updated_at DESC, media_id DESC
            LIMIT 1
            """
        )
    if value is None:
        return None
    return " ".join(str(value).split())[:600]


__all__ = (
    "_latest_ai_error",
    "_retire_weak_fallback_candidates",
)
