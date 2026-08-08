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
        return await self._claim_next(
            worker_id,
            target_object_id=self._target_object_id,
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