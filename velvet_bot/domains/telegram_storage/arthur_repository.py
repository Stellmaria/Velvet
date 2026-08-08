from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage.librarian_models import (
    LibrarianJob,
    StorageLibrarianError,
)
from velvet_bot.domains.telegram_storage.librarian_repository import (
    StorageLibrarianRepository,
)


_ARTHUR_ARCHIVE_ADVISORY_LOCK_KEY = 0x56454C5645544152


class ArthurStorageLibrarianRepository(StorageLibrarianRepository):
    """Storage repository with Arthur claim and archive-phase coordination."""

    def __init__(
        self,
        database: Database,
        *,
        target_object_id: int | None = None,
    ) -> None:
        super().__init__(database)
        self._arthur_database = database
        self._target_object_id = target_object_id

    @asynccontextmanager
    async def full_archive_phase(self) -> AsyncIterator[None]:
        """Hold one PostgreSQL session advisory lock for this archive phase."""

        async with self._arthur_database.acquire() as connection:
            acquired = await connection.fetchval(
                "SELECT pg_try_advisory_lock($1::BIGINT)",
                _ARTHUR_ARCHIVE_ADVISORY_LOCK_KEY,
            )
            if acquired is not True:
                raise StorageLibrarianError(
                    "Arthur full-archive phase is already active in another process."
                )
            try:
                yield
            finally:
                released = await connection.fetchval(
                    "SELECT pg_advisory_unlock($1::BIGINT)",
                    _ARTHUR_ARCHIVE_ADVISORY_LOCK_KEY,
                )
                if released is not True:
                    raise RuntimeError("Arthur full-archive advisory lock was not held.")

    async def full_archive_phase_active(self) -> bool:
        """Return cross-process archive phase state without leaving a lock behind."""

        async with self._arthur_database.acquire() as connection:
            acquired = await connection.fetchval(
                "SELECT pg_try_advisory_lock($1::BIGINT)",
                _ARTHUR_ARCHIVE_ADVISORY_LOCK_KEY,
            )
            if acquired is not True:
                return True
            released = await connection.fetchval(
                "SELECT pg_advisory_unlock($1::BIGINT)",
                _ARTHUR_ARCHIVE_ADVISORY_LOCK_KEY,
            )
            if released is not True:
                raise RuntimeError("Arthur archive probe failed to release advisory lock.")
            return False

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
