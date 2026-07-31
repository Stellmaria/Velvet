from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID
from velvet_bot.application.media_delivery import MediaDeliveryJob, MediaDeliveryStatus, MediaDeliveryStepStatus
from velvet_bot.application.media_tasks import task_payload_mapping, task_result_urls
from velvet_bot.database import Database
from velvet_bot.infrastructure.media_delivery_repository_helpers import _TERMINAL_STATUSES, _VIDEO_MODELS, _error_text, _job_from_rows, _json, _text, delivery_metadata, first_text, media_kind, optional_int

class MediaDeliveryRepositoryFinishMixin:

    async def mark_download(self, *, task_id: UUID, result_index: int, status: MediaDeliveryStepStatus, error: BaseException | None=None, content_type: str | None=None, file_name: str | None=None) -> None:
        url_status = 'expired' if status is MediaDeliveryStepStatus.EXPIRED else 'unreachable' if status is MediaDeliveryStepStatus.FAILED else 'available'
        async with self._database.acquire() as connection:
            await connection.execute("\n                UPDATE media_delivery_items\n                SET download_status=$3::VARCHAR,\n                    url_status=$4::VARCHAR,\n                    download_attempts=download_attempts+1,\n                    download_error=$5::TEXT,\n                    content_type=COALESCE($6::VARCHAR, content_type),\n                    file_name=COALESCE($7::TEXT, file_name),\n                    downloaded_at=CASE WHEN $3='success' THEN NOW() ELSE downloaded_at END,\n                    updated_at=NOW()\n                WHERE task_id=$1::UUID AND result_index=$2::INTEGER\n                ", task_id, int(result_index), status.value, url_status, _error_text(error), content_type, file_name)

    async def mark_channel(self, *, task_id: UUID, result_index: int, channel: str, status: MediaDeliveryStepStatus, error: BaseException | None=None) -> None:
        if channel not in {'original', 'preview'}:
            raise ValueError(f'Unsupported delivery channel: {channel}')
        status_column = f'{channel}_status'
        attempts_column = f'{channel}_attempts'
        error_column = f'{channel}_error'
        sent_column = f'{channel}_sent_at'
        async with self._database.acquire() as connection:
            await connection.execute(f"\n                UPDATE media_delivery_items\n                SET {status_column}=$3::VARCHAR,\n                    {attempts_column}={attempts_column}+1,\n                    {error_column}=$4::TEXT,\n                    {sent_column}=CASE WHEN $3='success' THEN NOW() ELSE {sent_column} END,\n                    updated_at=NOW()\n                WHERE task_id=$1::UUID AND result_index=$2::INTEGER\n                ", task_id, int(result_index), status.value, _error_text(error))

    async def mark_notification(self, *, task_id: UUID, status: MediaDeliveryStepStatus, error: BaseException | None=None) -> None:
        async with self._database.acquire() as connection:
            await connection.execute('\n                UPDATE media_delivery_jobs\n                SET notification_status=$2::VARCHAR,\n                    notification_error=$3::TEXT,\n                    updated_at=NOW()\n                WHERE task_id=$1::UUID\n                ', task_id, status.value, _error_text(error))

    async def finish(self, *, task_id: UUID, worker_id: str, status: MediaDeliveryStatus, last_error: str | None, retry_delay_seconds: int | None) -> None:
        retry_delay = max(0, int(retry_delay_seconds or 0))
        terminal = status.value in _TERMINAL_STATUSES
        async with self._database.acquire() as connection:
            await connection.execute("\n                UPDATE media_delivery_jobs\n                SET status=$3::VARCHAR,\n                    last_error=$4::TEXT,\n                    next_attempt_at=CASE\n                        WHEN $5::INTEGER > 0\n                            THEN NOW()+($5::INTEGER*INTERVAL '1 second')\n                        ELSE NOW()\n                    END,\n                    locked_by=NULL,\n                    locked_at=NULL,\n                    completed_at=CASE WHEN $6::BOOLEAN THEN NOW() ELSE NULL END,\n                    updated_at=NOW()\n                WHERE task_id=$1::UUID AND locked_by=$2::VARCHAR\n                ", task_id, _text(worker_id, 'media-delivery')[:160], status.value, (last_error or '')[-4000:] or None, retry_delay, terminal)

    async def reset_for_redelivery(self, *, task_id: UUID, chat_id: int) -> bool:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                result = await connection.execute("\n                    UPDATE media_delivery_jobs\n                    SET chat_id=$2::BIGINT,\n                        status='retry',\n                        attempt_count=0,\n                        notification_status='pending',\n                        notification_error=NULL,\n                        last_error=NULL,\n                        next_attempt_at=NOW(),\n                        locked_by=NULL,\n                        locked_at=NULL,\n                        completed_at=NULL,\n                        updated_at=NOW()\n                    WHERE task_id=$1::UUID\n                    ", task_id, int(chat_id))
                if not result.endswith(' 1'):
                    return False
                await connection.execute("\n                    UPDATE media_delivery_items\n                    SET url_status='available',\n                        download_status='pending',\n                        original_status='pending',\n                        preview_status='pending',\n                        download_error=NULL,\n                        original_error=NULL,\n                        preview_error=NULL,\n                        updated_at=NOW()\n                    WHERE task_id=$1::UUID\n                    ", task_id)
        return True

__all__ = ("MediaDeliveryRepositoryFinishMixin",)
