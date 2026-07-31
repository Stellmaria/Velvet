from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from velvet_bot.application.media_delivery_errors import (
    MediaDeliveryFailure,
    MediaDeliveryFailureKind,
    MediaDeliveryRecordedError,
    classify_media_delivery_error,
    raise_if_programming_error,
    recorded_media_delivery_error,
)
from velvet_bot.application.media_delivery_models import (
    DownloadedMedia,
    MediaDeliveryItem,
    MediaDeliveryJob,
    MediaDeliveryRepository,
    MediaDeliveryStatus,
    MediaDeliveryStepStatus,
    MediaDeliverySummary,
    MediaDeliveryTransport,
    MediaUrlExpired,
)

logger = logging.getLogger(__name__)
_ATTEMPTABLE = frozenset(
    {MediaDeliveryStepStatus.PENDING, MediaDeliveryStepStatus.FAILED}
)


class DeliverMediaResult:
    """Deliver originals and previews independently from durable state."""

    def __init__(
        self,
        *,
        repository: MediaDeliveryRepository,
        transport: MediaDeliveryTransport,
        worker_id: str = "media-delivery",
        max_attempts: int = 12,
    ) -> None:
        self._repository = repository
        self._transport = transport
        self._worker_id = worker_id.strip() or "media-delivery"
        self._max_attempts = max(1, int(max_attempts))

    async def execute(
        self,
        *,
        task_id: UUID | None = None,
    ) -> MediaDeliverySummary | None:
        job = await self._repository.claim(
            worker_id=self._worker_id,
            task_id=task_id,
        )
        if job is None:
            return None
        try:
            return await self._execute_claimed(job)
        except asyncio.CancelledError as error:
            await self._compensate_claim(
                job,
                error=error,
                status=MediaDeliveryStatus.RETRY,
                retry_delay_seconds=5,
            )
            raise
        except Exception as error:  # p2-approved-boundary: compensate-claimed-media-delivery
            failure = classify_media_delivery_error(error, phase="delivery_claim")
            retryable = (
                failure.kind is MediaDeliveryFailureKind.TRANSIENT
                and job.attempt_count < self._max_attempts
            )
            status = (
                MediaDeliveryStatus.RETRY
                if retryable
                else MediaDeliveryStatus.FAILED
            )
            await self._compensate_claim(
                job,
                error=error,
                status=status,
                retry_delay_seconds=(
                    self._retry_delay(job.attempt_count) if retryable else None
                ),
            )
            raise_if_programming_error(error, phase="delivery_claim")
            return self._summary_from_job(
                job,
                status=status,
                retry_scheduled=retryable,
            )

    async def _execute_claimed(self, job: MediaDeliveryJob) -> MediaDeliverySummary:
        original_states = {
            item.result_index: item.original_status for item in job.items
        }
        preview_states = {
            item.result_index: item.preview_status for item in job.items
        }
        download_states = {
            item.result_index: item.download_status for item in job.items
        }
        failures: list[MediaDeliveryRecordedError] = []

        if not job.items:
            failures.append(
                recorded_media_delivery_error(
                    ValueError("provider result has no URLs"),
                    phase="empty_result",
                )
            )

        for item in job.items:
            need_original = _attemptable(original_states[item.result_index])
            need_preview = _attemptable(preview_states[item.result_index])
            if not need_original and not need_preview:
                continue

            media = await self._download(
                job=job,
                item=item,
                need_original=need_original,
                need_preview=need_preview,
                original_states=original_states,
                preview_states=preview_states,
                download_states=download_states,
                failures=failures,
            )
            if media is None:
                continue

            if need_original:
                original_states[item.result_index] = await self._send_channel(
                    job=job,
                    item=item,
                    media=media,
                    channel="original",
                    failures=failures,
                )
            if need_preview:
                preview_states[item.result_index] = await self._send_channel(
                    job=job,
                    item=item,
                    media=media,
                    channel="preview",
                    failures=failures,
                )

        item_count = len(job.items)
        original_sent = _count_success(original_states)
        preview_sent = _count_success(preview_states)
        expired_items = sum(
            status is MediaDeliveryStepStatus.EXPIRED
            for status in download_states.values()
        )
        status, retryable = self._outcome(
            job=job,
            original_states=original_states,
            preview_states=preview_states,
            download_states=download_states,
        )

        notification_failure: MediaDeliveryRecordedError | None = None
        if (
            status is not MediaDeliveryStatus.RETRY
            and _attemptable(job.notification_status)
        ):
            notification_failure = await self._notify(
                job=job,
                text=self._notification_text(
                    status=status,
                    item_count=item_count,
                    original_sent=original_sent,
                    preview_sent=preview_sent,
                ),
            )
            if notification_failure is not None:
                failures.append(notification_failure)
                if (
                    notification_failure.failure.retryable
                    and job.attempt_count < self._max_attempts
                ):
                    status = MediaDeliveryStatus.RETRY
                    retryable = True

        delay = self._retry_delay(job.attempt_count) if retryable else None
        await self._repository.finish(
            task_id=job.task_id,
            worker_id=self._worker_id,
            status=status,
            error=failures[-1] if failures else None,
            retry_delay_seconds=delay,
        )
        logger.info(
            "media_delivery_outcome task=%s status=%s attempt=%s "
            "originals=%s previews=%s expired=%s",
            job.task_id,
            status.value,
            job.attempt_count,
            original_sent,
            preview_sent,
            expired_items,
        )
        return MediaDeliverySummary(
            task_id=job.task_id,
            status=status,
            item_count=item_count,
            original_sent=original_sent,
            preview_sent=preview_sent,
            expired_items=expired_items,
            retry_scheduled=retryable,
        )

    async def _download(
        self,
        *,
        job: MediaDeliveryJob,
        item: MediaDeliveryItem,
        need_original: bool,
        need_preview: bool,
        original_states: dict[int, MediaDeliveryStepStatus],
        preview_states: dict[int, MediaDeliveryStepStatus],
        download_states: dict[int, MediaDeliveryStepStatus],
        failures: list[MediaDeliveryRecordedError],
    ) -> DownloadedMedia | None:
        try:
            media = await self._transport.download(job=job, item=item)
        except asyncio.CancelledError:
            raise
        except MediaUrlExpired as error:
            recorded = recorded_media_delivery_error(error, phase="download")
            failures.append(recorded)
            download_states[item.result_index] = MediaDeliveryStepStatus.EXPIRED
            await self._repository.mark_download(
                task_id=job.task_id,
                result_index=item.result_index,
                status=MediaDeliveryStepStatus.EXPIRED,
                error=recorded,
            )
            if need_original:
                original_states[item.result_index] = MediaDeliveryStepStatus.EXPIRED
                await self._repository.mark_channel(
                    task_id=job.task_id,
                    result_index=item.result_index,
                    channel="original",
                    status=MediaDeliveryStepStatus.EXPIRED,
                    error=recorded,
                )
            if need_preview:
                preview_states[item.result_index] = MediaDeliveryStepStatus.EXPIRED
                await self._repository.mark_channel(
                    task_id=job.task_id,
                    result_index=item.result_index,
                    channel="preview",
                    status=MediaDeliveryStepStatus.EXPIRED,
                    error=recorded,
                )
            return None
        except Exception as error:  # p2-approved-boundary: classify-media-download-failure
            recorded = self._record_operational_failure(
                error,
                phase="download",
                failures=failures,
            )
            failed_status = _failure_status(recorded.failure)
            download_states[item.result_index] = failed_status
            await self._repository.mark_download(
                task_id=job.task_id,
                result_index=item.result_index,
                status=failed_status,
                error=recorded,
            )
            if need_original:
                original_states[item.result_index] = failed_status
                await self._repository.mark_channel(
                    task_id=job.task_id,
                    result_index=item.result_index,
                    channel="original",
                    status=failed_status,
                    error=recorded,
                )
            if need_preview and recorded.failure.retryable:
                preview_states[item.result_index] = await self._send_direct_preview(
                    job=job,
                    item=item,
                    failures=failures,
                )
            elif need_preview:
                preview_states[item.result_index] = failed_status
                await self._repository.mark_channel(
                    task_id=job.task_id,
                    result_index=item.result_index,
                    channel="preview",
                    status=failed_status,
                    error=recorded,
                )
            return None

        download_states[item.result_index] = MediaDeliveryStepStatus.SUCCESS
        await self._repository.mark_download(
            task_id=job.task_id,
            result_index=item.result_index,
            status=MediaDeliveryStepStatus.SUCCESS,
            content_type=media.content_type,
            file_name=media.file_name,
        )
        return media

    async def _send_channel(
        self,
        *,
        job: MediaDeliveryJob,
        item: MediaDeliveryItem,
        media: DownloadedMedia,
        channel: str,
        failures: list[MediaDeliveryRecordedError],
    ) -> MediaDeliveryStepStatus:
        await self._repository.mark_channel(
            task_id=job.task_id,
            result_index=item.result_index,
            channel=channel,
            status=MediaDeliveryStepStatus.UNCERTAIN,
        )
        try:
            if channel == "original":
                await self._transport.send_original(job=job, item=item, media=media)
            elif channel == "preview":
                await self._transport.send_preview(job=job, item=item, media=media)
            else:
                raise AssertionError(f"unsupported channel: {channel}")
        except asyncio.CancelledError:
            raise
        except Exception as error:  # p2-approved-boundary: classify-telegram-channel-failure
            recorded = self._record_operational_failure(
                error,
                phase=f"{channel}_delivery",
                failures=failures,
            )
            status = _failure_status(recorded.failure)
            await self._repository.mark_channel(
                task_id=job.task_id,
                result_index=item.result_index,
                channel=channel,
                status=status,
                error=recorded,
            )
            return status

        await self._repository.mark_channel(
            task_id=job.task_id,
            result_index=item.result_index,
            channel=channel,
            status=MediaDeliveryStepStatus.SUCCESS,
        )
        return MediaDeliveryStepStatus.SUCCESS

    async def _send_direct_preview(
        self,
        *,
        job: MediaDeliveryJob,
        item: MediaDeliveryItem,
        failures: list[MediaDeliveryRecordedError],
    ) -> MediaDeliveryStepStatus:
        await self._repository.mark_channel(
            task_id=job.task_id,
            result_index=item.result_index,
            channel="preview",
            status=MediaDeliveryStepStatus.UNCERTAIN,
        )
        try:
            await self._transport.send_direct_preview(job=job, item=item)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # p2-approved-boundary: classify-direct-preview-failure
            recorded = self._record_operational_failure(
                error,
                phase="direct_preview",
                failures=failures,
            )
            status = _failure_status(recorded.failure)
            await self._repository.mark_channel(
                task_id=job.task_id,
                result_index=item.result_index,
                channel="preview",
                status=status,
                error=recorded,
            )
            return status

        await self._repository.mark_channel(
            task_id=job.task_id,
            result_index=item.result_index,
            channel="preview",
            status=MediaDeliveryStepStatus.SUCCESS,
        )
        return MediaDeliveryStepStatus.SUCCESS

    async def _notify(
        self,
        *,
        job: MediaDeliveryJob,
        text: str,
    ) -> MediaDeliveryRecordedError | None:
        await self._repository.mark_notification(
            task_id=job.task_id,
            status=MediaDeliveryStepStatus.UNCERTAIN,
        )
        try:
            await self._transport.notify(job=job, text=text)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # p2-approved-boundary: classify-delivery-notification-failure
            recorded = self._record_operational_failure(
                error,
                phase="notification",
                failures=[],
            )
            await self._repository.mark_notification(
                task_id=job.task_id,
                status=_failure_status(recorded.failure),
                error=recorded,
            )
            return recorded

        await self._repository.mark_notification(
            task_id=job.task_id,
            status=MediaDeliveryStepStatus.SUCCESS,
        )
        return None

    async def _compensate_claim(
        self,
        job: MediaDeliveryJob,
        *,
        error: BaseException,
        status: MediaDeliveryStatus,
        retry_delay_seconds: int | None,
    ) -> None:
        recorded = recorded_media_delivery_error(error, phase="claim_compensation")
        try:
            await self._repository.finish(
                task_id=job.task_id,
                worker_id=self._worker_id,
                status=status,
                error=recorded,
                retry_delay_seconds=retry_delay_seconds,
            )
        except asyncio.CancelledError:
            raise
        except Exception as compensation_error:  # p2-approved-boundary: preserve-lease-recovery-on-compensation-failure
            failure = classify_media_delivery_error(
                compensation_error,
                phase="claim_compensation_write",
            )
            logger.error(
                "media_delivery_compensation_failed task=%s code=%s fingerprint=%s",
                job.task_id,
                failure.code,
                failure.fingerprint,
            )
            raise_if_programming_error(
                compensation_error,
                phase="claim_compensation_write",
            )

    @staticmethod
    def _record_operational_failure(
        error: BaseException,
        *,
        phase: str,
        failures: list[MediaDeliveryRecordedError],
    ) -> MediaDeliveryRecordedError:
        raise_if_programming_error(error, phase=phase)
        recorded = recorded_media_delivery_error(error, phase=phase)
        failures.append(recorded)
        return recorded

    def _outcome(
        self,
        *,
        job: MediaDeliveryJob,
        original_states: dict[int, MediaDeliveryStepStatus],
        preview_states: dict[int, MediaDeliveryStepStatus],
        download_states: dict[int, MediaDeliveryStepStatus],
    ) -> tuple[MediaDeliveryStatus, bool]:
        item_count = len(job.items)
        original_sent = _count_success(original_states)
        preview_sent = _count_success(preview_states)
        all_channels = (
            item_count > 0
            and original_sent >= item_count
            and preview_sent >= item_count
        )
        any_delivery = original_sent > 0 or preview_sent > 0
        all_expired = (
            item_count > 0
            and all(
                state is MediaDeliveryStepStatus.EXPIRED
                for state in download_states.values()
            )
            and not any_delivery
        )
        retryable_steps = any(
            _attemptable(state)
            for state in (*original_states.values(), *preview_states.values())
        )
        retryable = (
            item_count > 0
            and not all_channels
            and not all_expired
            and retryable_steps
            and job.attempt_count < self._max_attempts
        )
        if retryable:
            return MediaDeliveryStatus.RETRY, True
        if all_channels:
            return MediaDeliveryStatus.DELIVERED, False
        if all_expired:
            return MediaDeliveryStatus.EXPIRED, False
        if any_delivery:
            return MediaDeliveryStatus.PARTIAL, False
        return MediaDeliveryStatus.FAILED, False

    @staticmethod
    def _summary_from_job(
        job: MediaDeliveryJob,
        *,
        status: MediaDeliveryStatus,
        retry_scheduled: bool,
    ) -> MediaDeliverySummary:
        return MediaDeliverySummary(
            task_id=job.task_id,
            status=status,
            item_count=len(job.items),
            original_sent=sum(
                item.original_status is MediaDeliveryStepStatus.SUCCESS
                for item in job.items
            ),
            preview_sent=sum(
                item.preview_status is MediaDeliveryStepStatus.SUCCESS
                for item in job.items
            ),
            expired_items=sum(
                item.download_status is MediaDeliveryStepStatus.EXPIRED
                for item in job.items
            ),
            retry_scheduled=retry_scheduled,
        )

    @staticmethod
    def _retry_delay(attempt_count: int) -> int:
        return min(900, 5 * 2 ** max(0, int(attempt_count) - 1))

    @staticmethod
    def _notification_text(
        *,
        status: MediaDeliveryStatus,
        item_count: int,
        original_sent: int,
        preview_sent: int,
    ) -> str:
        if status is MediaDeliveryStatus.DELIVERED:
            return (
                f"Доставка завершена: оригиналы {original_sent}/{item_count}, "
                f"предпросмотры {preview_sent}/{item_count}."
            )
        if status is MediaDeliveryStatus.PARTIAL:
            return (
                "Генерация завершена, но доставка выполнена частично: "
                f"оригиналы {original_sent}/{item_count}, "
                f"предпросмотры {preview_sent}/{item_count}. "
                "Новая платная генерация не запускалась."
            )
        if status is MediaDeliveryStatus.EXPIRED:
            return (
                "Сохранённые URL результата истекли до завершения доставки. "
                "Новая платная генерация не запускалась."
            )
        return (
            "Генерация завершена у провайдера, но файл пока не доставлен. "
            "Результат и история попыток сохранены; новая платная генерация "
            "не запускалась."
        )


def _attemptable(status: MediaDeliveryStepStatus) -> bool:
    return status in _ATTEMPTABLE


def _count_success(states: dict[int, MediaDeliveryStepStatus]) -> int:
    return sum(status is MediaDeliveryStepStatus.SUCCESS for status in states.values())


def _failure_status(failure: MediaDeliveryFailure) -> MediaDeliveryStepStatus:
    return (
        MediaDeliveryStepStatus.FAILED
        if failure.retryable
        else MediaDeliveryStepStatus.SKIPPED
    )


__all__ = ("DeliverMediaResult",)
