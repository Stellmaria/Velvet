from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from uuid import UUID

from velvet_bot.application.media_delivery_models import (
    MediaDeliveryItem,
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


@dataclass(slots=True)
class _DeliveryProgress:
    original_sent: int = 0
    preview_sent: int = 0
    expired_items: int = 0
    uncertain_channels: int = 0
    retryable_failure: bool = False
    terminal_failure: bool = False
    errors: list[str] = field(default_factory=list)

    def absorb(self, outcome: _ChannelOutcome, *, channel: str) -> None:
        if channel == "original":
            self.original_sent += int(outcome.sent)
        elif channel == "preview":
            self.preview_sent += int(outcome.sent)
        self.uncertain_channels += int(outcome.uncertain)
        self.retryable_failure = (
            self.retryable_failure or outcome.retryable_failure
        )
        self.terminal_failure = self.terminal_failure or outcome.terminal_failure


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

        progress = self._initial_progress(job)
        if progress.uncertain_channels:
            progress.errors.append("delivery_state_uncertain")
        if not job.items:
            progress.errors.append("provider_result_has_no_urls")
            progress.terminal_failure = True

        try:
            for item in job.items:
                await self._process_item(job, item, progress)
        except asyncio.CancelledError:
            await self._finish_cancelled(job)
            raise

        status, retryable = self._choose_status(job, progress)
        if status is not MediaDeliveryStatus.RETRY:
            notification = await self._deliver_notification(
                job=job,
                status=status,
                progress=progress,
            )
            progress.absorb(notification, channel="notification")
            if (
                notification.retryable_failure
                and not progress.uncertain_channels
                and job.attempt_count < self._max_attempts
            ):
                status = MediaDeliveryStatus.RETRY
                retryable = True

        delay = self._retry_delay(job.attempt_count) if retryable else None
        await self._repository.finish(
            task_id=job.task_id,
            worker_id=self._worker_id,
            status=status,
            last_error=(
                " | ".join(progress.errors)[-4000:]
                if progress.errors
                else None
            ),
            retry_delay_seconds=delay,
        )
        self._log_outcome(job, status, progress)
        return MediaDeliverySummary(
            task_id=job.task_id,
            status=status,
            item_count=len(job.items),
            original_sent=progress.original_sent,
            preview_sent=progress.preview_sent,
            expired_items=progress.expired_items,
            retry_scheduled=retryable,
            uncertain_channels=progress.uncertain_channels,
        )

    async def _process_item(
        self,
        job: MediaDeliveryJob,
        item: MediaDeliveryItem,
        progress: _DeliveryProgress,
    ) -> None:
        need_original = item.original_status in _RETRYABLE_STEP_STATUSES
        need_preview = item.preview_status in _RETRYABLE_STEP_STATUSES
        if not need_original and not need_preview:
            return

        try:
            media = await self._transport.download(job=job, item=item)
        except asyncio.CancelledError:
            raise
        except MediaUrlExpired as error:
            await self._expire_item(
                job=job,
                item=item,
                error=error,
                need_original=need_original,
                need_preview=need_preview,
            )
            progress.expired_items += 1
            progress.errors.append(error.code)
            return
        except MediaDeliveryTransportError as error:
            await self._handle_download_failure(
                job=job,
                item=item,
                error=error,
                need_original=need_original,
                need_preview=need_preview,
                progress=progress,
            )
            return

        await self._repository.mark_download(
            task_id=job.task_id,
            result_index=item.result_index,
            status=MediaDeliveryStepStatus.SUCCESS,
            content_type=media.content_type,
            file_name=media.file_name,
        )
        if need_original:
            progress.absorb(
                await self._deliver_channel(
                    job=job,
                    result_index=item.result_index,
                    channel="original",
                    operation=lambda: self._transport.send_original(
                        job=job,
                        item=item,
                        media=media,
                    ),
                    errors=progress.errors,
                ),
                channel="original",
            )
        if need_preview:
            progress.absorb(
                await self._deliver_channel(
                    job=job,
                    result_index=item.result_index,
                    channel="preview",
                    operation=lambda: self._transport.send_preview(
                        job=job,
                        item=item,
                        media=media,
                    ),
                    errors=progress.errors,
                ),
                channel="preview",
            )

    async def _handle_download_failure(
        self,
        *,
        job: MediaDeliveryJob,
        item: MediaDeliveryItem,
        error: MediaDeliveryTransportError,
        need_original: bool,
        need_preview: bool,
        progress: _DeliveryProgress,
    ) -> None:
        progress.errors.append(error.code)
        progress.retryable_failure = progress.retryable_failure or error.retryable
        progress.terminal_failure = progress.terminal_failure or not error.retryable
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
                status=(
                    MediaDeliveryStepStatus.FAILED
                    if error.retryable
                    else MediaDeliveryStepStatus.EXPIRED
                ),
                error=error,
            )
        if need_preview:
            progress.absorb(
                await self._deliver_channel(
                    job=job,
                    result_index=item.result_index,
                    channel="preview",
                    operation=lambda: self._transport.send_direct_preview(
                        job=job,
                        item=item,
                    ),
                    errors=progress.errors,
                ),
                channel="preview",
            )

    async def _expire_item(
        self,
        *,
        job: MediaDeliveryJob,
        item: MediaDeliveryItem,
        error: MediaUrlExpired,
        need_original: bool,
        need_preview: bool,
    ) -> None:
        await self._repository.mark_download(
            task_id=job.task_id,
            result_index=item.result_index,
            status=MediaDeliveryStepStatus.EXPIRED,
            error=error,
        )
        for channel, needed in (
            ("original", need_original),
            ("preview", need_preview),
        ):
            if needed:
                await self._repository.mark_channel(
                    task_id=job.task_id,
                    result_index=item.result_index,
                    channel=channel,
                    status=MediaDeliveryStepStatus.EXPIRED,
                    error=error,
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
        progress: _DeliveryProgress,
    ) -> _ChannelOutcome:
        if job.notification_status is MediaDeliveryStepStatus.SUCCESS:
            return _ChannelOutcome(sent=True)
        if job.notification_status in _AMBIGUOUS_STEP_STATUSES:
            progress.errors.append("notification_state_uncertain")
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
                    item_count=len(job.items),
                    original_sent=progress.original_sent,
                    preview_sent=progress.preview_sent,
                ),
            )
        except asyncio.CancelledError:
            await self._mark_notification_uncertain(
                job=job,
                error_code="transport_cancelled_during_notification",
            )
            raise
        except MediaDeliveryTransportError as error:
            progress.errors.append(error.code)
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
            progress.errors.append(error.code)
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

    def _choose_status(
        self,
        job: MediaDeliveryJob,
        progress: _DeliveryProgress,
    ) -> tuple[MediaDeliveryStatus, bool]:
        item_count = len(job.items)
        all_channels = (
            item_count > 0
            and progress.original_sent >= item_count
            and progress.preview_sent >= item_count
        )
        any_delivery = progress.original_sent > 0 or progress.preview_sent > 0
        all_expired = (
            item_count > 0
            and progress.expired_items >= item_count
            and not any_delivery
            and progress.uncertain_channels == 0
        )
        retryable = (
            item_count > 0
            and not all_channels
            and not all_expired
            and progress.uncertain_channels == 0
            and not progress.terminal_failure
            and (progress.retryable_failure or not progress.errors)
            and job.attempt_count < self._max_attempts
        )
        if retryable:
            return MediaDeliveryStatus.RETRY, True
        if all_channels:
            return MediaDeliveryStatus.DELIVERED, False
        if all_expired:
            return MediaDeliveryStatus.EXPIRED, False
        if any_delivery or progress.uncertain_channels:
            return MediaDeliveryStatus.PARTIAL, False
        return MediaDeliveryStatus.FAILED, False

    @staticmethod
    def _initial_progress(job: MediaDeliveryJob) -> _DeliveryProgress:
        return _DeliveryProgress(
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
            uncertain_channels=(
                sum(
                    item.original_status in _AMBIGUOUS_STEP_STATUSES
                    for item in job.items
                )
                + sum(
                    item.preview_status in _AMBIGUOUS_STEP_STATUSES
                    for item in job.items
                )
                + int(job.notification_status in _AMBIGUOUS_STEP_STATUSES)
            ),
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

    @staticmethod
    def _log_outcome(
        job: MediaDeliveryJob,
        status: MediaDeliveryStatus,
        progress: _DeliveryProgress,
    ) -> None:
        logger.info(
            "media_delivery_outcome task=%s status=%s attempt=%s "
            "originals=%s previews=%s expired=%s uncertain=%s",
            job.task_id,
            status.value,
            job.attempt_count,
            progress.original_sent,
            progress.preview_sent,
            progress.expired_items,
            progress.uncertain_channels,
        )


__all__ = ("DeliverMediaResult",)
