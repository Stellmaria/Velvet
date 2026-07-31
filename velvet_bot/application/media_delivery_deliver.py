from __future__ import annotations

import asyncio
import logging
from uuid import UUID
from velvet_bot.application.media_delivery_models import DownloadedMedia, MediaDeliveryJob, MediaDeliveryRepository, MediaDeliveryStatus, MediaDeliveryStepStatus, MediaDeliverySummary, MediaDeliveryTransport, MediaUrlExpired
logger = logging.getLogger(__name__)

class DeliverMediaResult:
    """Deliver originals and previews independently from durable state."""

    def __init__(self, *, repository: MediaDeliveryRepository, transport: MediaDeliveryTransport, worker_id: str='media-delivery', max_attempts: int=12) -> None:
        self._repository = repository
        self._transport = transport
        self._worker_id = worker_id.strip() or 'media-delivery'
        self._max_attempts = max(1, int(max_attempts))

    async def execute(self, *, task_id: UUID | None=None) -> MediaDeliverySummary | None:
        job = await self._repository.claim(worker_id=self._worker_id, task_id=task_id)
        if job is None:
            return None
        original_sent = sum((item.original_status is MediaDeliveryStepStatus.SUCCESS for item in job.items))
        preview_sent = sum((item.preview_status is MediaDeliveryStepStatus.SUCCESS for item in job.items))
        expired_items = sum((item.download_status is MediaDeliveryStepStatus.EXPIRED for item in job.items))
        errors: list[str] = []
        try:
            if not job.items:
                errors.append('Провайдер завершил задачу без URL результата.')
            for item in job.items:
                need_original = item.original_status is not MediaDeliveryStepStatus.SUCCESS
                need_preview = item.preview_status is not MediaDeliveryStepStatus.SUCCESS
                if not need_original and (not need_preview):
                    continue
                try:
                    media = await self._transport.download(job=job, item=item)
                    await self._repository.mark_download(task_id=job.task_id, result_index=item.result_index, status=MediaDeliveryStepStatus.SUCCESS, content_type=media.content_type, file_name=media.file_name)
                except asyncio.CancelledError:
                    raise
                except MediaUrlExpired as error:
                    expired_items += 1
                    errors.append(str(error))
                    await self._repository.mark_download(task_id=job.task_id, result_index=item.result_index, status=MediaDeliveryStepStatus.EXPIRED, error=error)
                    if need_original:
                        await self._repository.mark_channel(task_id=job.task_id, result_index=item.result_index, channel='original', status=MediaDeliveryStepStatus.EXPIRED, error=error)
                    if need_preview:
                        await self._repository.mark_channel(task_id=job.task_id, result_index=item.result_index, channel='preview', status=MediaDeliveryStepStatus.EXPIRED, error=error)
                    continue
                except Exception as error:
                    errors.append(str(error))
                    await self._repository.mark_download(task_id=job.task_id, result_index=item.result_index, status=MediaDeliveryStepStatus.FAILED, error=error)
                    if need_original:
                        await self._repository.mark_channel(task_id=job.task_id, result_index=item.result_index, channel='original', status=MediaDeliveryStepStatus.FAILED, error=error)
                    if need_preview:
                        try:
                            await self._transport.send_direct_preview(job=job, item=item)
                        except asyncio.CancelledError:
                            raise
                        except Exception as preview_error:
                            errors.append(str(preview_error))
                            await self._repository.mark_channel(task_id=job.task_id, result_index=item.result_index, channel='preview', status=MediaDeliveryStepStatus.FAILED, error=preview_error)
                        else:
                            preview_sent += 1
                            await self._repository.mark_channel(task_id=job.task_id, result_index=item.result_index, channel='preview', status=MediaDeliveryStepStatus.SUCCESS)
                    continue
                if need_original:
                    try:
                        await self._transport.send_original(job=job, item=item, media=media)
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        errors.append(str(error))
                        await self._repository.mark_channel(task_id=job.task_id, result_index=item.result_index, channel='original', status=MediaDeliveryStepStatus.FAILED, error=error)
                    else:
                        original_sent += 1
                        await self._repository.mark_channel(task_id=job.task_id, result_index=item.result_index, channel='original', status=MediaDeliveryStepStatus.SUCCESS)
                if need_preview:
                    try:
                        await self._transport.send_preview(job=job, item=item, media=media)
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        errors.append(str(error))
                        await self._repository.mark_channel(task_id=job.task_id, result_index=item.result_index, channel='preview', status=MediaDeliveryStepStatus.FAILED, error=error)
                    else:
                        preview_sent += 1
                        await self._repository.mark_channel(task_id=job.task_id, result_index=item.result_index, channel='preview', status=MediaDeliveryStepStatus.SUCCESS)
        except asyncio.CancelledError:
            await self._repository.finish(task_id=job.task_id, worker_id=self._worker_id, status=MediaDeliveryStatus.RETRY, last_error='Delivery worker cancelled.', retry_delay_seconds=5)
            raise
        item_count = len(job.items)
        all_original = item_count > 0 and original_sent >= item_count
        all_preview = item_count > 0 and preview_sent >= item_count
        all_channels = all_original and all_preview
        any_delivery = original_sent > 0 or preview_sent > 0
        all_expired = item_count > 0 and expired_items >= item_count and (not any_delivery)
        retryable = item_count > 0 and (not all_channels) and (not all_expired) and (job.attempt_count < self._max_attempts)
        notification_error: BaseException | None = None
        if retryable:
            status = MediaDeliveryStatus.RETRY
        elif all_channels:
            status = MediaDeliveryStatus.DELIVERED
        elif all_expired:
            status = MediaDeliveryStatus.EXPIRED
        elif any_delivery:
            status = MediaDeliveryStatus.PARTIAL
        else:
            status = MediaDeliveryStatus.FAILED
        if status is not MediaDeliveryStatus.RETRY:
            try:
                await self._transport.notify(job=job, text=self._notification_text(status=status, item_count=item_count, original_sent=original_sent, preview_sent=preview_sent))
            except asyncio.CancelledError:
                raise
            except Exception as error:
                notification_error = error
                errors.append(str(error))
                await self._repository.mark_notification(task_id=job.task_id, status=MediaDeliveryStepStatus.FAILED, error=error)
            else:
                await self._repository.mark_notification(task_id=job.task_id, status=MediaDeliveryStepStatus.SUCCESS)
        if notification_error is not None and job.attempt_count < self._max_attempts:
            status = MediaDeliveryStatus.RETRY
            retryable = True
        delay = self._retry_delay(job.attempt_count) if retryable else None
        await self._repository.finish(task_id=job.task_id, worker_id=self._worker_id, status=status, last_error=' | '.join(errors)[-4000:] if errors else None, retry_delay_seconds=delay)
        logger.info('media_delivery_outcome task=%s status=%s attempt=%s originals=%s previews=%s expired=%s', job.task_id, status.value, job.attempt_count, original_sent, preview_sent, expired_items)
        return MediaDeliverySummary(task_id=job.task_id, status=status, item_count=item_count, original_sent=original_sent, preview_sent=preview_sent, expired_items=expired_items, retry_scheduled=retryable)

    @staticmethod
    def _retry_delay(attempt_count: int) -> int:
        return min(900, 5 * 2 ** max(0, int(attempt_count) - 1))

    @staticmethod
    def _notification_text(*, status: MediaDeliveryStatus, item_count: int, original_sent: int, preview_sent: int) -> str:
        if status is MediaDeliveryStatus.DELIVERED:
            return f'Доставка завершена: оригиналы {original_sent}/{item_count}, предпросмотры {preview_sent}/{item_count}.'
        if status is MediaDeliveryStatus.PARTIAL:
            return f'Генерация завершена, но доставка выполнена частично: оригиналы {original_sent}/{item_count}, предпросмотры {preview_sent}/{item_count}. Новая платная генерация не запускалась.'
        if status is MediaDeliveryStatus.EXPIRED:
            return 'Сохранённые URL результата истекли до завершения доставки. Новая платная генерация не запускалась.'
        return 'Генерация завершена у провайдера, но файл пока не доставлен. Результат и история попыток сохранены; новая платная генерация не запускалась.'

__all__ = ("DeliverMediaResult",)
