from __future__ import annotations

from uuid import UUID

from velvet_bot.application.media_delivery import (
    MediaDeliveryJob,
    MediaDeliveryStateConflict,
)
from velvet_bot.infrastructure.media_delivery_repository_helpers import (
    _error_text,
    _job_from_rows,
    _text,
)


class MediaDeliveryRepositoryClaimMixin:
    async def claim_resolution(
        self,
        *,
        worker_id: str,
        task_id: UUID | None = None,
    ) -> MediaDeliveryJob | None:
        normalized_worker = _text(worker_id, "media-result-resolver")[:160]
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                WITH candidate AS (
                    SELECT job.task_id
                    FROM media_delivery_jobs AS job
                    WHERE ($2::UUID IS NULL OR job.task_id=$2::UUID)
                      AND job.status='provider_success'
                      AND job.next_attempt_at <= NOW()
                      AND (
                          job.locked_at IS NULL
                          OR job.locked_at < NOW() - INTERVAL '15 minutes'
                      )
                    ORDER BY
                        CASE WHEN job.task_id=$2::UUID THEN 0 ELSE 1 END,
                        job.next_attempt_at ASC,
                        job.created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE media_delivery_jobs AS job
                SET result_resolution_attempts=job.result_resolution_attempts+1,
                    locked_by=$1::VARCHAR,
                    locked_at=NOW(),
                    updated_at=NOW()
                FROM candidate
                WHERE job.task_id=candidate.task_id
                RETURNING job.*
                """,
                normalized_worker,
                task_id,
            )
            if row is None:
                return None
            item_rows = await connection.fetch(
                """
                SELECT * FROM media_delivery_items
                WHERE task_id=$1::UUID
                ORDER BY result_index
                """,
                row["task_id"],
            )
        return _job_from_rows(row, item_rows)

    async def finish_resolution(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        error: BaseException | None,
        retry_delay_seconds: int | None,
        terminal: bool = False,
    ) -> None:
        retry_delay = max(0, int(retry_delay_seconds or 0))
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE media_delivery_jobs
                SET status=CASE
                        WHEN $5::BOOLEAN THEN 'failed'
                        ELSE 'provider_success'
                    END,
                    result_resolution_error=$3::TEXT,
                    last_error=$3::TEXT,
                    next_attempt_at=CASE
                        WHEN $4::INTEGER > 0
                            THEN NOW()+($4::INTEGER*INTERVAL '1 second')
                        ELSE NOW()
                    END,
                    locked_by=NULL,
                    locked_at=NULL,
                    completed_at=CASE WHEN $5::BOOLEAN THEN NOW() ELSE NULL END,
                    updated_at=NOW()
                WHERE task_id=$1::UUID
                  AND locked_by=$2::VARCHAR
                  AND status='provider_success'
                """,
                task_id,
                _text(worker_id, "media-result-resolver")[:160],
                _error_text(error),
                retry_delay,
                bool(terminal),
            )
        if not result.endswith(" 1"):
            raise MediaDeliveryStateConflict(
                "finish_resolution",
                "Result resolution lock was lost before completion.",
            )

    async def claim(
        self,
        *,
        worker_id: str,
        task_id: UUID | None = None,
    ) -> MediaDeliveryJob | None:
        normalized_worker = _text(worker_id, "media-delivery")[:160]
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                WITH candidate AS (
                    SELECT job.task_id
                    FROM media_delivery_jobs AS job
                    WHERE ($2::UUID IS NULL OR job.task_id=$2::UUID)
                      AND (
                        job.status IN ('result_resolved', 'retry')
                        OR (
                            job.status='delivering'
                            AND job.locked_at < NOW() - INTERVAL '15 minutes'
                        )
                      )
                      AND job.next_attempt_at <= NOW()
                    ORDER BY
                        CASE WHEN job.task_id=$2::UUID THEN 0 ELSE 1 END,
                        job.next_attempt_at ASC,
                        job.created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE media_delivery_jobs AS job
                SET status='delivering',
                    attempt_count=job.attempt_count+1,
                    locked_by=$1::VARCHAR,
                    locked_at=NOW(),
                    updated_at=NOW()
                FROM candidate
                WHERE job.task_id=candidate.task_id
                RETURNING job.*
                """,
                normalized_worker,
                task_id,
            )
            if row is None:
                return None
            item_rows = await connection.fetch(
                """
                SELECT * FROM media_delivery_items
                WHERE task_id=$1::UUID
                ORDER BY result_index ASC
                """,
                row["task_id"],
            )
        return _job_from_rows(row, item_rows)


__all__ = ("MediaDeliveryRepositoryClaimMixin",)
