from __future__ import annotations

from uuid import UUID

from velvet_bot.application.media_delivery import (
    MediaDeliveryStateConflict,
    MediaDeliveryStatus,
    MediaDeliveryStepStatus,
)
from velvet_bot.infrastructure.media_delivery_repository_helpers import (
    _TERMINAL_STATUSES,
    _error_text,
    _text,
)


class MediaDeliveryRepositoryFinishMixin:
    async def mark_download(
        self,
        *,
        task_id: UUID,
        result_index: int,
        status: MediaDeliveryStepStatus,
        error: BaseException | None = None,
        content_type: str | None = None,
        file_name: str | None = None,
    ) -> None:
        if status in {
            MediaDeliveryStepStatus.SENDING,
            MediaDeliveryStepStatus.UNCERTAIN,
        }:
            raise ValueError(f"Unsupported download status: {status.value}")
        url_status = (
            "expired"
            if status is MediaDeliveryStepStatus.EXPIRED
            else "unreachable"
            if status is MediaDeliveryStepStatus.FAILED
            else "available"
        )
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE media_delivery_items
                SET download_status=$3::VARCHAR,
                    url_status=$4::VARCHAR,
                    download_attempts=download_attempts+1,
                    download_error=$5::TEXT,
                    content_type=COALESCE($6::VARCHAR, content_type),
                    file_name=COALESCE($7::TEXT, file_name),
                    downloaded_at=CASE
                        WHEN $3='success' THEN NOW()
                        ELSE downloaded_at
                    END,
                    updated_at=NOW()
                WHERE task_id=$1::UUID
                  AND result_index=$2::INTEGER
                  AND download_status <> 'success'
                """,
                task_id,
                int(result_index),
                status.value,
                url_status,
                _error_text(error),
                content_type,
                file_name,
            )
        _require_updated(result, "mark_download")

    async def mark_channel(
        self,
        *,
        task_id: UUID,
        result_index: int,
        channel: str,
        status: MediaDeliveryStepStatus,
        error: BaseException | None = None,
    ) -> None:
        if channel not in {"original", "preview"}:
            raise ValueError(f"Unsupported delivery channel: {channel}")
        if status is MediaDeliveryStepStatus.PENDING:
            raise ValueError("PENDING is assigned only by reset_for_redelivery.")
        status_column = f"{channel}_status"
        attempts_column = f"{channel}_attempts"
        error_column = f"{channel}_error"
        sent_column = f"{channel}_sent_at"
        if status is MediaDeliveryStepStatus.SENDING:
            predicate = f"{status_column} IN ('pending','failed')"
            attempts_update = f"{attempts_column}={attempts_column}+1"
        elif status in {
            MediaDeliveryStepStatus.SUCCESS,
            MediaDeliveryStepStatus.FAILED,
            MediaDeliveryStepStatus.UNCERTAIN,
        }:
            predicate = f"{status_column}='sending'"
            attempts_update = f"{attempts_column}={attempts_column}"
        elif status is MediaDeliveryStepStatus.EXPIRED:
            predicate = f"{status_column} NOT IN ('success','uncertain')"
            attempts_update = f"{attempts_column}={attempts_column}"
        elif status is MediaDeliveryStepStatus.SKIPPED:
            predicate = f"{status_column}='pending'"
            attempts_update = f"{attempts_column}={attempts_column}"
        else:
            raise ValueError(f"Unsupported delivery channel status: {status.value}")
        async with self._database.acquire() as connection:
            result = await connection.execute(
                f"""
                UPDATE media_delivery_items
                SET {status_column}=$3::VARCHAR,
                    {attempts_update},
                    {error_column}=$4::TEXT,
                    {sent_column}=CASE
                        WHEN $3='success' THEN NOW()
                        ELSE {sent_column}
                    END,
                    updated_at=NOW()
                WHERE task_id=$1::UUID
                  AND result_index=$2::INTEGER
                  AND {predicate}
                """,
                task_id,
                int(result_index),
                status.value,
                _error_text(error),
            )
        _require_updated(result, f"mark_{channel}_{status.value}")

    async def mark_notification(
        self,
        *,
        task_id: UUID,
        status: MediaDeliveryStepStatus,
        error: BaseException | None = None,
    ) -> None:
        if status is MediaDeliveryStepStatus.PENDING:
            raise ValueError("PENDING is assigned only by reset_for_redelivery.")
        if status is MediaDeliveryStepStatus.SENDING:
            predicate = "notification_status IN ('pending','failed')"
        elif status in {
            MediaDeliveryStepStatus.SUCCESS,
            MediaDeliveryStepStatus.FAILED,
            MediaDeliveryStepStatus.UNCERTAIN,
        }:
            predicate = "notification_status='sending'"
        elif status in {
            MediaDeliveryStepStatus.EXPIRED,
            MediaDeliveryStepStatus.SKIPPED,
        }:
            predicate = "notification_status NOT IN ('success','uncertain')"
        else:
            raise ValueError(f"Unsupported notification status: {status.value}")
        async with self._database.acquire() as connection:
            result = await connection.execute(
                f"""
                UPDATE media_delivery_jobs
                SET notification_status=$2::VARCHAR,
                    notification_error=$3::TEXT,
                    updated_at=NOW()
                WHERE task_id=$1::UUID
                  AND {predicate}
                """,
                task_id,
                status.value,
                _error_text(error),
            )
        _require_updated(result, f"mark_notification_{status.value}")

    async def finish(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        status: MediaDeliveryStatus,
        last_error: str | None,
        retry_delay_seconds: int | None,
    ) -> None:
        retry_delay = max(0, int(retry_delay_seconds or 0))
        terminal = status.value in _TERMINAL_STATUSES
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE media_delivery_jobs
                SET status=$3::VARCHAR,
                    last_error=$4::TEXT,
                    next_attempt_at=CASE
                        WHEN $5::INTEGER > 0
                            THEN NOW()+($5::INTEGER*INTERVAL '1 second')
                        ELSE NOW()
                    END,
                    locked_by=NULL,
                    locked_at=NULL,
                    completed_at=CASE WHEN $6::BOOLEAN THEN NOW() ELSE NULL END,
                    updated_at=NOW()
                WHERE task_id=$1::UUID
                  AND locked_by=$2::VARCHAR
                  AND status='delivering'
                """,
                task_id,
                _text(worker_id, "media-delivery")[:160],
                status.value,
                (last_error or "")[-4000:] or None,
                retry_delay,
                terminal,
            )
        _require_updated(result, "finish_delivery")

    async def reset_for_redelivery(self, *, task_id: UUID, chat_id: int) -> bool:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                result = await connection.execute(
                    """
                    UPDATE media_delivery_jobs
                    SET chat_id=$2::BIGINT,
                        status='retry',
                        attempt_count=0,
                        notification_status='pending',
                        notification_error=NULL,
                        last_error=NULL,
                        next_attempt_at=NOW(),
                        locked_by=NULL,
                        locked_at=NULL,
                        completed_at=NULL,
                        updated_at=NOW()
                    WHERE task_id=$1::UUID
                    """,
                    task_id,
                    int(chat_id),
                )
                if not result.endswith(" 1"):
                    return False
                await connection.execute(
                    """
                    UPDATE media_delivery_items
                    SET url_status='available',
                        download_status='pending',
                        original_status='pending',
                        preview_status='pending',
                        download_error=NULL,
                        original_error=NULL,
                        preview_error=NULL,
                        updated_at=NOW()
                    WHERE task_id=$1::UUID
                    """,
                    task_id,
                )
        return True


def _require_updated(result: str, operation: str) -> None:
    if result.endswith(" 1"):
        return
    raise MediaDeliveryStateConflict(
        operation,
        f"Media delivery transition {operation} did not update exactly one row.",
    )


__all__ = ("MediaDeliveryRepositoryFinishMixin",)
