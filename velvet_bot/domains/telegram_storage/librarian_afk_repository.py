from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage.librarian_models import LibrarianJob
from velvet_bot.domains.telegram_storage.librarian_repository import (
    StorageLibrarianRepository,
)


async def recover_stale_running_jobs(
    database: Database,
    *,
    stale_after_seconds: int,
) -> tuple[int, int]:
    """Release orphaned Librarian claims without erasing attempt history."""
    if stale_after_seconds <= 0:
        raise ValueError("stale_after_seconds должен быть больше нуля.")
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            UPDATE telegram_storage_analysis_jobs
            SET status = CASE
                    WHEN attempts >= max_attempts THEN 'failed'
                    ELSE 'queued'
                END,
                available_at = NOW(),
                last_error = CASE
                    WHEN attempts >= max_attempts
                        THEN COALESCE(
                            NULLIF(last_error, ''),
                            'Storage Librarian worker lease expired after maximum attempts.'
                        )
                    ELSE last_error
                END,
                locked_at = NULL,
                worker_id = NULL,
                finished_at = CASE
                    WHEN attempts >= max_attempts THEN NOW()
                    ELSE NULL
                END,
                updated_at = NOW()
            WHERE status = 'running'
              AND (
                  locked_at IS NULL
                  OR locked_at <= NOW() - ($1::INTEGER * INTERVAL '1 second')
              )
            RETURNING status
            """,
            int(stale_after_seconds),
        )
    requeued = sum(1 for row in rows if str(row["status"]) == "queued")
    failed = sum(1 for row in rows if str(row["status"]) == "failed")
    return requeued, failed


class StorageLibrarianAfkRepository(StorageLibrarianRepository):
    """Queue view that cannot claim objects at or below the AFK cutoff."""

    def __init__(self, database: Database, *, min_object_id: int) -> None:
        super().__init__(database)
        cutoff = int(min_object_id)
        if cutoff <= 0:
            raise ValueError(
                "STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID должен быть больше нуля."
            )
        self._min_object_id = cutoff

    async def claim_next(self, worker_id: str) -> LibrarianJob | None:
        return await self._claim_next(
            worker_id,
            min_object_id=self._min_object_id,
        )


__all__ = ("StorageLibrarianAfkRepository", "recover_stale_running_jobs")