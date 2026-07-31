from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID
from velvet_bot.application.media_delivery import MediaDeliveryJob, MediaDeliveryStatus, MediaDeliveryStepStatus
from velvet_bot.application.media_tasks import task_payload_mapping, task_result_urls
from velvet_bot.database import Database
from velvet_bot.infrastructure.media_delivery_repository_helpers import _TERMINAL_STATUSES, _VIDEO_MODELS, _error_text, _job_from_rows, _json, _text, delivery_metadata, first_text, media_kind, optional_int

class MediaDeliveryRepositoryClaimMixin:

    async def claim_resolution(self, *, worker_id: str, task_id: UUID | None=None) -> MediaDeliveryJob | None:
        normalized_worker = _text(worker_id, 'media-result-resolver')[:160]
        async with self._database.acquire() as connection:
            row = await connection.fetchrow("\n                WITH candidate AS (\n                    SELECT job.task_id\n                    FROM media_delivery_jobs AS job\n                    WHERE ($2::UUID IS NULL OR job.task_id=$2::UUID)\n                      AND job.status='provider_success'\n                      AND job.next_attempt_at <= NOW()\n                      AND (job.locked_at IS NULL OR job.locked_at < NOW() - INTERVAL '15 minutes')\n                    ORDER BY\n                        CASE WHEN job.task_id=$2::UUID THEN 0 ELSE 1 END,\n                        job.next_attempt_at ASC,\n                        job.created_at ASC\n                    FOR UPDATE SKIP LOCKED\n                    LIMIT 1\n                )\n                UPDATE media_delivery_jobs AS job\n                SET result_resolution_attempts=job.result_resolution_attempts+1,\n                    locked_by=$1::VARCHAR,\n                    locked_at=NOW(),\n                    updated_at=NOW()\n                FROM candidate\n                WHERE job.task_id=candidate.task_id\n                RETURNING job.*\n                ", normalized_worker, task_id)
            if row is None:
                return None
            item_rows = await connection.fetch('SELECT * FROM media_delivery_items WHERE task_id=$1::UUID ORDER BY result_index', row['task_id'])
        return _job_from_rows(row, item_rows)

    async def finish_resolution(self, *, task_id: UUID, worker_id: str, error: BaseException | None, retry_delay_seconds: int | None, terminal: bool=False) -> None:
        retry_delay = max(0, int(retry_delay_seconds or 0))
        async with self._database.acquire() as connection:
            await connection.execute("\n                UPDATE media_delivery_jobs\n                SET status=CASE WHEN $5::BOOLEAN THEN 'failed' ELSE 'provider_success' END,\n                    result_resolution_error=$3::TEXT,\n                    last_error=$3::TEXT,\n                    next_attempt_at=CASE\n                        WHEN $4::INTEGER > 0 THEN NOW()+($4::INTEGER*INTERVAL '1 second')\n                        ELSE NOW()\n                    END,\n                    locked_by=NULL,\n                    locked_at=NULL,\n                    completed_at=CASE WHEN $5::BOOLEAN THEN NOW() ELSE NULL END,\n                    updated_at=NOW()\n                WHERE task_id=$1::UUID AND locked_by=$2::VARCHAR\n                ", task_id, _text(worker_id, 'media-result-resolver')[:160], _error_text(error), retry_delay, bool(terminal))

    async def claim(self, *, worker_id: str, task_id: UUID | None=None) -> MediaDeliveryJob | None:
        normalized_worker = _text(worker_id, 'media-delivery')[:160]
        async with self._database.acquire() as connection:
            row = await connection.fetchrow("\n                WITH candidate AS (\n                    SELECT job.task_id\n                    FROM media_delivery_jobs AS job\n                    WHERE ($2::UUID IS NULL OR job.task_id=$2::UUID)\n                      AND (\n                        job.status IN ('result_resolved', 'retry')\n                        OR (\n                            job.status='delivering'\n                            AND job.locked_at < NOW() - INTERVAL '15 minutes'\n                        )\n                      )\n                      AND job.next_attempt_at <= NOW()\n                    ORDER BY\n                        CASE WHEN job.task_id=$2::UUID THEN 0 ELSE 1 END,\n                        job.next_attempt_at ASC,\n                        job.created_at ASC\n                    FOR UPDATE SKIP LOCKED\n                    LIMIT 1\n                )\n                UPDATE media_delivery_jobs AS job\n                SET status='delivering',\n                    attempt_count=job.attempt_count+1,\n                    locked_by=$1::VARCHAR,\n                    locked_at=NOW(),\n                    updated_at=NOW()\n                FROM candidate\n                WHERE job.task_id=candidate.task_id\n                RETURNING job.*\n                ", normalized_worker, task_id)
            if row is None:
                return None
            item_rows = await connection.fetch('\n                SELECT * FROM media_delivery_items\n                WHERE task_id=$1::UUID\n                ORDER BY result_index ASC\n                ', row['task_id'])
        return _job_from_rows(row, item_rows)

__all__ = ("MediaDeliveryRepositoryClaimMixin",)
