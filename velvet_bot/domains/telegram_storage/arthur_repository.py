from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage.librarian_models import LibrarianJob
from velvet_bot.domains.telegram_storage.librarian_repository import (
    StorageLibrarianRepository,
)


class ArthurStorageLibrarianRepository(StorageLibrarianRepository):
    """Storage repository with an optional exact-object claim boundary."""

    def __init__(
        self,
        database: Database,
        *,
        target_object_id: int | None = None,
    ) -> None:
        super().__init__(database)
        self._arthur_database = database
        self._target_object_id = target_object_id

    async def claim_next(self, worker_id: str) -> LibrarianJob | None:
        if self._target_object_id is None:
            return await super().claim_next(worker_id)
        async with self._arthur_database.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE telegram_storage_analysis_jobs
                SET status = 'running',
                    attempts = attempts + 1,
                    locked_at = NOW(),
                    worker_id = $2::TEXT,
                    updated_at = NOW()
                WHERE storage_object_id = $1::BIGINT
                  AND status = 'queued'
                  AND available_at <= NOW()
                  AND attempts < max_attempts
                RETURNING id, storage_object_id, attempts, max_attempts
                """,
                int(self._target_object_id),
                worker_id,
            )
        if row is None:
            return None
        return LibrarianJob(
            job_id=int(row["id"]),
            storage_object_id=int(row["storage_object_id"]),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
        )

    async def job_status(self, object_id: int) -> dict[str, object] | None:
        async with self._arthur_database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT storage_object_id, status, attempts, max_attempts,
                       available_at, last_error, locked_at, worker_id,
                       hermes_run_id, finished_at, updated_at
                FROM telegram_storage_analysis_jobs
                WHERE storage_object_id = $1::BIGINT
                """,
                int(object_id),
            )
        return dict(row) if row is not None else None


__all__ = ("ArthurStorageLibrarianRepository",)
