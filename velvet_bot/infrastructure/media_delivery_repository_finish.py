from __future__ import annotations

from uuid import UUID

from velvet_bot.application.media_delivery import (
    MediaDeliveryInvariantError,
    MediaDeliveryStatus,
    MediaDeliveryStepStatus,
)
from velvet_bot.infrastructure.media_delivery_repository_helpers import (
    _TERMINAL_STATUSES,
    _error_fields,
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
        message, code, fingerprint = _error_fields(error, phase="download")
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE media_delivery_items
                SET download_status=CASE
                        WHEN download_status='success' THEN 'success'
                        WHEN download_status='expired' THEN 'expired'
                        ELSE $3::VARCHAR
                    END,
                    url_status=CASE
                        WHEN download_status='success' THEN url_status
                        WHEN download_status='expired' THEN 'expired'
                        WHEN $3='expired' THEN 'expired'
                        WHEN $3='failed' THEN 'unreachable'
                        WHEN $3='success' THEN 'available'
                        ELSE url_status
                    END,
                    download_attempts=download_attempts+CASE
                        WHEN download_status IN ('pending','failed') THEN 1
                        ELSE 0
                    END,
                    download_error=CASE
                        WHEN download_status IN ('success','expired') THEN download_error
                        WHEN $3='success' THEN NULL
                        ELSE $4::TEXT
                    END,
                    download_error_code=CASE
                        WHEN download_status IN ('success','expired') THEN download_error_code
                        WHEN $3='success' THEN NULL
                        ELSE $5::VARCHAR
                    END,
                    download_error_fingerprint=CASE
                        WHEN download_status IN ('success','expired')
                            THEN download_error_fingerprint
                        WHEN $3='success' THEN NULL
                        ELSE $6::VARCHAR
                    END,
                    content_type=COALESCE($7::VARCHAR, content_type),
                    file_name=COALESCE($8::TEXT, file_name),
                    downloaded_at=CASE
                        WHEN $3='success' THEN COALESCE(downloaded_at, NOW())
                        ELSE downloaded_at
                    END,
                    updated_at=NOW()
                WHERE task_id=$1::UUID AND result_index=$2::INTEGER
                """,
                task_id,
                int(result_index),
                status.value,
                message,
                code,
                fingerprint,
                content_type,
                file_name,
            )
        _require_updated(result, operation="mark_download")

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
            raise MediaDeliveryInvariantError(
                f"Unsupported delivery channel contract: {channel!r}"
            )
        status_column = f"{channel}_status"
        attempts_column = f"{channel}_attempts"
        error_column = f"{channel}_error"
        error_code_column = f"{channel}_error_code"
        error_fingerprint_column = f"{channel}_error_fingerprint"
        sent_column = f"{channel}_sent_at"
        message, code, fingerprint = _error_fields(
            error,
            phase=f"{channel}_delivery",
        )
        async with self._database.acquire() as connection:
            result = await connection.execute(
                f"""
                UPDATE media_delivery_items
                SET {status_column}=CASE
                        WHEN {status_column}='success' THEN 'success'
                        WHEN {status_column}='expired' THEN 'expired'
                        ELSE $3::VARCHAR
                    END,
                    {attempts_column}={attempts_column}+CASE
                        WHEN $3='uncertain'
                         AND {status_column} IN ('pending','failed') THEN 1
                        ELSE 0
                    END,
                    {error_column}=CASE
                        WHEN {status_column} IN ('success','expired')
                            THEN {error_column}
                        WHEN $3='success' THEN NULL
                        ELSE $4::TEXT
                    END,
                    {error_code_column}=CASE
                        WHEN {status_column} IN ('success','expired')
                            THEN {error_code_column}
                        WHEN $3='success' THEN NULL
                        ELSE $5::VARCHAR
                    END,
                    {error_fingerprint_column}=CASE
                        WHEN {status_column} IN ('success','expired')
                            THEN {error_fingerprint_column}
                        WHEN $3='success' THEN NULL
                        ELSE $6::VARCHAR
                    END,
                    {sent_column}=CASE
                        WHEN $3='success' THEN COALESCE({sent_column}, NOW())
                        ELSE {sent_column}
                    END,
                    updated_at=NOW()
                WHERE task_id=$1::UUID AND result_index=$2::INTEGER
                """,
                task_id,
                int(result_index),
                status.value,
                message,
                code,
                fingerprint,
            )
        _require_updated(result, operation=f"mark_{channel}")

    async def mark_notification(
        self,
        *,
        task_id: UUID,
        status: MediaDeliveryStepStatus,
        error: BaseException | None = None,
    ) -> None:
        message, code, fingerprint = _error_fields(error, phase="notification")
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE media_delivery_jobs
                SET notification_status=CASE
                        WHEN notification_status='success' THEN 'success'
                        WHEN notification_status='expired' THEN 'expired'
                        ELSE $2::VARCHAR
                    END,
                    notification_error=CASE
                        WHEN notification_status IN ('success','expired')
                            THEN notification_error
                        WHEN $2='success' THEN NULL
                        ELSE $3::TEXT
                    END,
                    notification_error_code=CASE
                        WHEN notification_status IN ('success','expired')
                            THEN notification_error_code
                        WHEN $2='success' THEN NULL
                        ELSE $4::VARCHAR
                    END,
                    notification_error_fingerprint=CASE
                        WHEN notification_status IN ('success','expired')
                            THEN notification_error_fingerprint
                        WHEN $2='success' THEN NULL
                        ELSE $5::VARCHAR
                    END,
                    updated_at=NOW()
                WHERE task_id=$1::UUID
                """,
                task_id,
                status.value,
                message,
                code,
                fingerprint,
            )
        _require_updated(result, operation="mark_notification")

    async def finish(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        status: MediaDeliveryStatus,
        error: BaseException | None,
        retry_delay_seconds: int | None,
    ) -> None:
        retry_delay = max(0, int(retry_delay_seconds or 0))
        terminal = status.value in _TERMINAL_STATUSES
        message, code, fingerprint = _error_fields(error, phase="delivery")
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE media_delivery_jobs
                SET status=CASE
                        WHEN status IN ('delivered','partial','expired','failed')
                            THEN status
                        ELSE $3::VARCHAR
                    END,
                    last_error=CASE
                        WHEN status IN ('delivered','partial','expired','failed')
                            THEN last_error
                        ELSE $4::TEXT
                    END,
                    last_error_code=CASE
                        WHEN status IN ('delivered','partial','expired','failed')
                            THEN last_error_code
                        ELSE $5::VARCHAR
                    END,
                    last_error_fingerprint=CASE
                        WHEN status IN ('delivered','partial','expired','failed')
                            THEN last_error_fingerprint
                        ELSE $6::VARCHAR
                    END,
                    next_attempt_at=CASE
                        WHEN $7::INTEGER > 0
                            THEN NOW()+($7::INTEGER*INTERVAL '1 second')
                        ELSE NOW()
                    END,
                    locked_by=NULL,
                    locked_at=NULL,
                    completed_at=CASE
                        WHEN status IN ('delivered','partial','expired','failed')
                            THEN completed_at
                        WHEN $8::BOOLEAN THEN COALESCE(completed_at, NOW())
                        ELSE NULL
                    END,
                    updated_at=NOW()
                WHERE task_id=$1::UUID AND locked_by=$2::VARCHAR
                """,
                task_id,
                _text(worker_id, "media-delivery")[:160],
                status.value,
                message,
                code,
                fingerprint,
                retry_delay,
                terminal,
            )
        _require_updated(result, operation="finish_delivery_claim")

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
                        notification_error_code=NULL,
                        notification_error_fingerprint=NULL,
                        last_error=NULL,
                        last_error_code=NULL,
                        last_error_fingerprint=NULL,
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
                        download_error_code=NULL,
                        download_error_fingerprint=NULL,
                        original_error=NULL,
                        original_error_code=NULL,
                        original_error_fingerprint=NULL,
                        preview_error=NULL,
                        preview_error_code=NULL,
                        preview_error_fingerprint=NULL,
                        updated_at=NOW()
                    WHERE task_id=$1::UUID
                    """,
                    task_id,
                )
        return True


def _require_updated(result: str, *, operation: str) -> None:
    if not str(result).endswith(" 1"):
        raise MediaDeliveryInvariantError(
            f"Media delivery state transition lost its row: {operation}"
        )


__all__ = ("MediaDeliveryRepositoryFinishMixin",)
