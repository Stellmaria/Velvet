from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage.librarian_models import LibrarianJob
from velvet_bot.domains.telegram_storage.librarian_repository import (
    StorageLibrarianRepository,
)


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
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                WITH picked AS (
                    SELECT id
                    FROM telegram_storage_analysis_jobs
                    WHERE status = 'queued'
                      AND storage_object_id > $2::BIGINT
                      AND available_at <= NOW()
                      AND attempts < max_attempts
                    ORDER BY priority DESC, available_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE telegram_storage_analysis_jobs AS job
                SET status = 'running',
                    attempts = job.attempts + 1,
                    locked_at = NOW(),
                    worker_id = $1::TEXT,
                    updated_at = NOW()
                FROM picked
                WHERE job.id = picked.id
                RETURNING job.id, job.storage_object_id,
                          job.attempts, job.max_attempts
                """,
                worker_id,
                self._min_object_id,
            )
        if row is None:
            return None
        return LibrarianJob(
            job_id=int(row["id"]),
            storage_object_id=int(row["storage_object_id"]),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
        )


__all__ = ("StorageLibrarianAfkRepository",)
