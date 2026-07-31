from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from uuid import UUID

from velvet_bot.application.media_delivery_errors import (
    MediaDeliveryFailureKind,
    MediaDeliveryTransientError,
    classify_media_delivery_error,
    raise_if_programming_error,
    recorded_media_delivery_error,
)
from velvet_bot.application.media_delivery_models import (
    MediaDeliveryRepository,
    ProviderResultResolver,
)

logger = logging.getLogger(__name__)


class ResolveProviderResult:
    """Persist provider identity and resolve missing result URLs durably."""

    def __init__(
        self,
        repository: MediaDeliveryRepository,
        provider_resolver: ProviderResultResolver | None = None,
        *,
        worker_id: str = "media-result-resolver",
        max_attempts: int = 12,
    ) -> None:
        self._repository = repository
        self._provider_resolver = provider_resolver
        self._worker_id = worker_id.strip() or "media-result-resolver"
        self._max_attempts = max(1, int(max_attempts))

    async def provider_submitted(
        self,
        *,
        task_id: UUID,
        provider: str,
        provider_task_id: str,
        chat_id: int | None,
        media_kind: str,
        request: Mapping[str, object],
    ) -> None:
        await self._repository.record_provider_submission(
            task_id=task_id,
            provider=provider,
            provider_task_id=provider_task_id,
            chat_id=chat_id,
            media_kind=media_kind,
            request=request,
        )

    async def provider_succeeded(
        self,
        *,
        task_id: UUID,
        provider: str,
        provider_task_id: str,
        chat_id: int | None,
        media_kind: str,
        request: Mapping[str, object],
        result_urls: tuple[str, ...],
    ) -> None:
        await self._repository.record_provider_success(
            task_id=task_id,
            provider=provider,
            provider_task_id=provider_task_id,
            chat_id=chat_id,
            media_kind=media_kind,
            request=request,
            result_urls=result_urls,
        )

    async def execute(self, *, task_id: UUID | None = None) -> bool:
        if self._provider_resolver is None:
            return False
        job = await self._repository.claim_resolution(
            worker_id=self._worker_id,
            task_id=task_id,
        )
        if job is None:
            return False
        try:
            urls = await self._provider_resolver.resolve(
                provider=job.provider,
                provider_task_id=job.provider_task_id,
            )
            if not urls:
                raise MediaDeliveryTransientError(
                    "provider_result_not_ready",
                    "Провайдер пока не вернул URL готового результата.",
                )
            await self._repository.record_provider_success(
                task_id=job.task_id,
                provider=job.provider,
                provider_task_id=job.provider_task_id,
                chat_id=job.chat_id,
                media_kind=job.media_kind,
                request=job.request,
                result_urls=urls,
            )
            logger.info(
                "media_delivery_resolution task=%s provider=%s outcome=resolved count=%s",
                job.task_id,
                job.provider,
                len(urls),
            )
            return True
        except asyncio.CancelledError as error:
            await self._finish_claim(
                job.task_id,
                error=error,
                retry_delay_seconds=5,
                terminal=False,
            )
            raise
        except Exception as error:  # p2-approved-boundary: compensate-claimed-result-resolution
            failure = classify_media_delivery_error(
                error,
                phase="result_resolution",
            )
            terminal = (
                failure.kind is MediaDeliveryFailureKind.TERMINAL
                or job.attempt_count >= self._max_attempts
            )
            delay = None if terminal else self._retry_delay(job.attempt_count)
            await self._finish_claim(
                job.task_id,
                error=error,
                retry_delay_seconds=delay,
                terminal=terminal,
            )
            logger.warning(
                "media_delivery_resolution task=%s provider=%s outcome=%s "
                "code=%s fingerprint=%s",
                job.task_id,
                job.provider,
                "failed" if terminal else "retry",
                failure.code,
                failure.fingerprint,
            )
            raise_if_programming_error(error, phase="result_resolution")
            return False

    async def _finish_claim(
        self,
        task_id: UUID,
        *,
        error: BaseException,
        retry_delay_seconds: int | None,
        terminal: bool,
    ) -> None:
        recorded = recorded_media_delivery_error(
            error,
            phase="result_resolution_claim",
        )
        try:
            await self._repository.finish_resolution(
                task_id=task_id,
                worker_id=self._worker_id,
                error=recorded,
                retry_delay_seconds=retry_delay_seconds,
                terminal=terminal,
            )
        except asyncio.CancelledError:
            raise
        except Exception as compensation_error:  # p2-approved-boundary: preserve-resolution-lease-recovery
            failure = classify_media_delivery_error(
                compensation_error,
                phase="result_resolution_compensation",
            )
            logger.error(
                "media_delivery_resolution_compensation_failed task=%s "
                "code=%s fingerprint=%s",
                task_id,
                failure.code,
                failure.fingerprint,
            )
            raise_if_programming_error(
                compensation_error,
                phase="result_resolution_compensation",
            )

    @staticmethod
    def _retry_delay(attempt_count: int) -> int:
        return min(900, 5 * 2 ** max(0, int(attempt_count) - 1))


__all__ = ("ResolveProviderResult",)
