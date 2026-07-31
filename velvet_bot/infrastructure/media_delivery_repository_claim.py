from __future__ import annotations

from uuid import UUID

from velvet_bot.application.media_delivery import (
    MediaDeliveryInvariantError,
    MediaDeliveryJob,
)
from velvet_bot.infrastructure.media_delivery_repository_helpers import (
    _error_fields,
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
                SELECT *
                FROM media_delivery_items
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
        message, code, fingerprint = _error_fields(
            error,
            phase="result_resolution",
        )
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE media_delivery_jobs
                SET status=CASE
                        WHEN status IN ('delivered','partial','expired','failed')
                            THEN status
                        WHEN $7::BOOLEAN THEN 'failed'
                        ELSE 'provider_success'
                    END,
                    result_resolution_error=CASE
                        WHEN status IN ('delivered','partial','expired','failed')
                            THEN result_resolution_error
                        ELSE $3::TEXT
                    END,
                    result_resolution_error_code=CASE
                        WHEN status IN ('delivered','partial','expired','failed')
                            THEN result_resolution_error_code
                        ELSE $4::VARCHAR
                    END,
                    result_resolution_error_fingerprint=CASE
                        WHEN status IN ('delivered','partial','expired','failed')
                            THEN result_resolution_error_fingerprint
                        ELSE $5::VARCHAR
                    END,
                    last_error=CASE
                        WHEN status IN ('delivered','partial','expired','failed')
                            THEN last_error
                        ELSE $3::TEXT
                    END,
                    last_error_code=CASE
                        WHEN status IN ('delivered','partial','expired','failed')
                            THEN last_error_code
                        ELSE $4::VARCHAR
                    END,
                    last_error_fingerprint=CASE
                        WHEN status IN ('delivered','partial','expired','failed')
                            THEN last_error_fingerprint
                        ELSE $5::VARCHAR
                    END,
                    next_attempt_at=CASE
                        WHEN $6::INTEGER > 0
                            THEN NOW()+($6::INTEGER*INTERVAL '1 second')
                        ELSE NOW()
                    END,
                    locked_by=NULL,
                    locked_at=NULL,
                    completed_at=CASE
                        WHEN status IN ('delivered','partial','expired','failed')
                            THEN completed_at
                        WHEN $7::BOOLEAN THEN COALESCE(completed_at, NOW())
                        ELSE NULL
                    END,
                    updated_at=NOW()
                WHERE task_id=$1::UUID AND locked_by=$2::VARCHAR
                """,
                task_id,
                _text(worker_id, "media-result-resolver")[:160],
                message,
                code,
                fingerprint,
                retry_delay,
                bool(terminal),
            )
        _require_updated(result, operation="finish_resolution_claim")

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
                SELECT *
                FROM media_delivery_items
                WHERE task_id=$1::UUID
                ORDER BY result_index ASC
                """,
                row["task_id"],
            )
        return _job_from_rows(row, item_rows)


def _require_updated(result: str, *, operation: str) -> None:
    if not str(result).endswith(" 1"):
        raise MediaDeliveryInvariantError(
            f"Media delivery state transition lost its row: {operation}"
        )


__all__ = ("MediaDeliveryRepositoryClaimMixin",)
