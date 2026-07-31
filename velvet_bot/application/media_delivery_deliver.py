from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from velvet_bot.application.media_delivery_models import (
    DownloadedMedia,
    MediaDeliveryJob,
    MediaDeliveryRepository,
    MediaDeliveryRepositoryError,
    MediaDeliveryStatus,
    MediaDeliveryStepStatus,
    MediaDeliverySummary,
    MediaDeliveryTransport,
    MediaDeliveryTransportError,
    MediaUrlExpired,
)

logger = logging.getLogger(__name__)
_RETRYABLE_STEP_STATUSES = frozenset(
    {MediaDeliveryStepStatus.PENDING, MediaDeliveryStepStatus.FAILED}
)
_AMBIGUOUS_STEP_STATUSES = frozenset(
    {MediaDeliveryStepStatus.SENDING, MediaDeliveryStepStatus.UNCERTAIN}
)


@dataclass(frozen=True, slots=True)
class _ChannelOutcome:
    sent: bool = False
    uncertain: bool = False
    retryable_failure: bool = False
    terminal_failure: bool = False


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

        original_sent = sum(
            item.original_status is MediaDeliveryStepStatus.SUCCESS
            for item in job.items
        )
        preview_sent = sum(
            item.preview_status is MediaDeliveryStepStatus.SUCCESS
            for item in job.items
        )
        expired_items = sum(
            item.download_status is MediaDeliveryStepStatus.EXPIRED
            for item in job.items
        )
        uncertain_channels = sum(
            item.original_status in _AMBIGUOUS_STEP_STATUSES
            for item in job.items
        ) + sum(
            item.preview_status in _AMBIGUOUS_STEP_STATUSES
            for item in job.items
        )
        errors: list[str] = []
        retryable_failure = False
        terminal_failure = False

        try:
            if not job.items:
                errors.append("provider_result_has_no_urls")
                terminal_failure = True

            for item in job.items:
                need_original = item.original_status in _RETRYABLE_STEP_STATUSES
                need_preview = item.preview_status in _RETRYABLE_STEP_STATUSES
                if not need_original and not need_preview:
                    continue

                try:
                    media = await self._transport.download(job=job, item=item)
                except asyncio.CancelledError:
                    raise
                except MediaUrlExpired as error:
                    expired_items += 1
                    errors.append(error.code)
                    await self._repository.mark_download(
                        task_id=job.task_id,
                        result_index=item.result_index,
                        status=MediaDeliveryStepStatus.EXPIRED,
                        error=error,
                    )
                    if need_original:
                        await self._repository.mark_channel(
                            task_id=job.task_id,
                            result_index=item.result_index,
                            channel="original",
                            status=MediaDeliveryStepStatus.EXPIRED,
                            error=error,
                        )
                    if need_preview:
                        await self._repository.mark_channel(
                            task_id=job.task_id,
                            result_index=item.result_index,
                            channel="preview",
                            status=MediaDeliveryStepStatus.EXPIRED,
                            error=error,
                        )
                    continue
                except MediaDeliveryTransportError as error:
                    errors.append(error.code)
                    retryable_failure = retryable_failure or error.retryable
                    terminal_failure = terminal_failure or not error.retryable
                    await self._repository.mark_download(
                        task_id=job.task_id,
                        result_index=item.result_index,
                        status=MediaDeliveryStepStatus.FAILED,
                        error=error,
                    )
                    if need_original:
                        await self._repository.mark_channel(
                            task_id=job.task_id,
                            result_index=item.result_index,
                            channel="original",
                            status=MediaDeliveryStepStatus.EXPIRED
                            if not error.retryable
                            else MediaDeliveryStepStatus.FAILED,
                            error=error,
                        )
                    if need_preview:
                        outcome = await self._deliver_channel(
                            job=job,
                            result_index=item.result_index,
                            channel="preview",
                            operation=lambda: self._transport.send_direct_preview(
                                job=job,
                                item=item,
                            ),
                            errors=errors,
                        )
                        preview_sent += int(outcome.sent)
                        uncertain_channels += int(outcome.uncertain)
                        retryable_failure = (
                            retryable_failure or outcome.retryable_failure
                        )
                        terminal_failure = (
                            terminal_failure or outcome.terminal_failure
                        )
                    continue

                await self._repository.mark_download(
                    task_id=job.task_id,
                    result_index=item.result_index,
                    status=MediaDeliveryStepStatus.SUCCESS,
                    content_type=media.content_type,
                    file_name=media.file_name,
                )

                if need_original:
                    outcome = await self._deliver_channel(
                        job=job,
                        result_index=item.result_index,
                        channel="original",
                        operation=lambda: self._transport.send_original(
                            job=job,
                            item=item,
                            media=media,
                        ),
                        errors=errors,
                    )
                    original_sent += int(outcome.sent)
                    uncertain_channels += int(outcome.uncertain)
                    retryable_failure = retryable_failure or outcome.retryable_failure
                    terminal_failure = terminal_failure or outcome.terminal_failure

                if need_preview:
                    outcome = await self._deliver_channel(
                        job=job,
                        result_index=item.result_index,
                        channel="preview",
                        operation=lambda: self._transport.send_preview(
                            job=job,
                            item=item,
                            media=media,
                        ),
                        errors=errors,
                    )
                    preview_sent += int(outcome.sent)
                    uncertain_channels += int(outcome.uncertain)
                    retryable_failure = retryable_failure or outcome.retryable_failure
                    terminal_failure = terminal_failure or outcome.terminal_failure
        except asyncio.CancelledError:
            await self._finish_cancelled(job)
            raise

        item_count = len(job.items)
        all_original = item_count > 0 and original_sent >= item_count
        all_preview = item_count > 0 and preview_sent >= item_count
        all_channels = all_original and all_preview
        any_delivery = original_sent > 0 or preview_sent > 0
        all_expired = (
            item_count > 0
            and expired_items >= item_count
            and not any_delivery
            and uncertain_channels == 0
        )
        retryable = (
            item_count > 0
            and not all_channels
            and not all_expired
            and uncertain_channels == 0
            and not terminal_failure
            and (retryable_failure or not errors)
            and job.attempt_count < self._max_attempts
        )

        if retryable:
            status = MediaDeliveryStatus.RETRY
        elif all_channels:
            status = MediaDeliveryStatus.DELIVERED
        elif all_expired:
            status = MediaDeliveryStatus.EXPIRED
        elif any_delivery or uncertain_channels:
            status = MediaDeliveryStatus.PARTIAL
        else:
            status = MediaDeliveryStatus.FAILED

        if status is not MediaDeliveryStatus.RETRY:
            notification = await self._deliver_notification(
                job=job,
                status=status,
                item_count=item_count,
                original_sent=original_sent,
                preview_sent=preview_sent,
                errors=errors,
            )
            uncertain_channels += int(notification.uncertain)
            retryable_failure = retryable_failure or notification.retryable_failure
            terminal_failure = terminal_failure or notification.terminal_failure
            if (
                notification.retryable_failure
                and uncertain_channels == 0
                and job.attempt_count < self._max_attempts
            ):
                status = MediaDeliveryStatus.RETRY
                retryable = True

        delay = self._retry_delay(job.attempt_count) if retryable else None
        await self._repository.finish(
            task_id=job.task_id,
            worker_id=self._worker_id,
            status=status,
            last_error=" | ".join(errors)[-4000:] if errors else None,
            retry_delay_seconds=delay,
        )
        logger.info(
            "media_delivery_outcome task=%s status=%s attempt=%s "
            "originals=%s previews=%s expired=%s uncertain=%s",
            job.task_id,
            status.value,
            job.attempt_count,
            original_sent,
            preview_sent,
            expired_items,
            uncertain_channels,
        )
        return MediaDeliverySummary(
            task_id=job.task_id,
            status=status,
            item_count=item_count,
            original_sent=original_sent,
            preview_sent=preview_sent,
            expired_items=expired_items,
            retry_scheduled=retryable,
            uncertain_channels=uncertain_channels,
        )

    async def _deliver_channel(
        self,
        *,
        job: MediaDeliveryJob,
        result_index: int,
        channel: str,
        operation: Callable[[], Awaitable[None]],
        errors: list[str],
    ) -> _ChannelOutcome:
        await self._repository.mark_channel(
            task_id=job.task_id,
            result_index=result_index,
            channel=channel,
            status=MediaDeliveryStepStatus.SENDING,
        )
        try:
            await operation()
        except asyncio.CancelledError:
            await self._mark_channel_uncertain(
                job=job,
                result_index=result_index,
                channel=channel,
                error_code="transport_cancelled_during_send",
            )
            raise
        except MediaDeliveryTransportError as error:
            errors.append(error.code)
            await self._repository.mark_channel(
                task_id=job.task_id,
                result_index=result_index,
                channel=channel,
                status=MediaDeliveryStepStatus.FAILED,
                error=error,
            )
            return _ChannelOutcome(
                retryable_failure=error.retryable,
                terminal_failure=not error.retryable,
            )

        try:
            await self._repository.mark_channel(
                task_id=job.task_id,
                result_index=result_index,
                channel=channel,
                status=MediaDeliveryStepStatus.SUCCESS,
            )
        except MediaDeliveryRepositoryError as error:
            errors.append(error.code)
            marked = await self._mark_channel_uncertain(
                job=job,
                result_index=result_index,
                channel=channel,
                error_code=error.code,
            )
            if not marked:
                raise
            return _ChannelOutcome(uncertain=True)
        return _ChannelOutcome(sent=True)

    async def _deliver_notification(
        self,
        *,
        job: MediaDeliveryJob,
        status: MediaDeliveryStatus,
        item_count: int,
        original_sent: int,
        preview_sent: int,
        errors: list[str],
    ) -> _ChannelOutcome:
        if job.notification_status is MediaDeliveryStepStatus.SUCCESS:
            return _ChannelOutcome(sent=True)
        if job.notification_status in _AMBIGUOUS_STEP_STATUSES:
            errors.append("notification_state_uncertain")
            return _ChannelOutcome(uncertain=True)
        if job.notification_status not in _RETRYABLE_STEP_STATUSES:
            return _ChannelOutcome()

        await self._repository.mark_notification(
            task_id=job.task_id,
            status=MediaDeliveryStepStatus.SENDING,
        )
        try:
            await self._transport.notify(
                job=job,
                text=self._notification_text(
                    status=status,
                    item_count=item_count,
                    original_sent=original_sent,
                    preview_sent=preview_sent,
                ),
            )
        except asyncio.CancelledError:
            await self._mark_notification_uncertain(
                job=job,
                error_code="transport_cancelled_during_notification",
            )
            raise
        except MediaDeliveryTransportError as error:
            errors.append(error.code)
            await self._repository.mark_notification(
                task_id=job.task_id,
                status=MediaDeliveryStepStatus.FAILED,
                error=error,
            )
            return _ChannelOutcome(
                retryable_failure=error.retryable,
                terminal_failure=not error.retryable,
            )

        try:
            await self._repository.mark_notification(
                task_id=job.task_id,
                status=MediaDeliveryStepStatus.SUCCESS,
            )
        except MediaDeliveryRepositoryError as error:
            errors.append(error.code)
            marked = await self._mark_notification_uncertain(
                job=job,
                error_code=error.code,
            )
            if not marked:
                raise
            return _ChannelOutcome(uncertain=True)
        return _ChannelOutcome(sent=True)

    async def _mark_channel_uncertain(
        self,
        *,
        job: MediaDeliveryJob,
        result_index: int,
        channel: str,
        error_code: str,
    ) -> bool:
        try:
            await self._repository.mark_channel(
                task_id=job.task_id,
                result_index=result_index,
                channel=channel,
                status=MediaDeliveryStepStatus.UNCERTAIN,
                error=RuntimeError(error_code),
            )
        except MediaDeliveryRepositoryError:
            logger.exception(
                "Could not persist ambiguous media channel task=%s index=%s channel=%s",
                job.task_id,
                result_index,
                channel,
            )
            return False
        return True

    async def _mark_notification_uncertain(
        self,
        *,
        job: MediaDeliveryJob,
        error_code: str,
    ) -> bool:
        try:
            await self._repository.mark_notification(
                task_id=job.task_id,
                status=MediaDeliveryStepStatus.UNCERTAIN,
                error=RuntimeError(error_code),
            )
        except MediaDeliveryRepositoryError:
            logger.exception(
                "Could not persist ambiguous media notification task=%s",
                job.task_id,
            )
            return False
        return True

    async def _finish_cancelled(self, job: MediaDeliveryJob) -> None:
        try:
            await self._repository.finish(
                task_id=job.task_id,
                worker_id=self._worker_id,
                status=MediaDeliveryStatus.RETRY,
                last_error="delivery_worker_cancelled",
                retry_delay_seconds=5,
            )
        except MediaDeliveryRepositoryError:
            logger.exception(
                "Could not release cancelled media delivery task=%s",
                job.task_id,
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
                "Генерация завершена, но доставка выполнена частично или её "
                f"статус неоднозначен: оригиналы {original_sent}/{item_count}, "
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


__all__ = ("DeliverMediaResult",)
