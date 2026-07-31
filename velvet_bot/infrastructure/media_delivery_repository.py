from __future__ import annotations

from collections.abc import Awaitable, Mapping
from typing import TypeVar
from uuid import UUID

import asyncpg

from velvet_bot.application.media_delivery import (
    MediaDeliveryJob,
    MediaDeliveryRepositoryError,
    MediaDeliveryStatus,
    MediaDeliveryStepStatus,
)
from velvet_bot.database import Database
from velvet_bot.infrastructure.media_delivery_repository_backfill import (
    MediaDeliveryRepositoryBackfillMixin,
)
from velvet_bot.infrastructure.media_delivery_repository_claim import (
    MediaDeliveryRepositoryClaimMixin,
)
from velvet_bot.infrastructure.media_delivery_repository_finish import (
    MediaDeliveryRepositoryFinishMixin,
)
from velvet_bot.infrastructure.media_delivery_repository_helpers import (
    delivery_metadata,
    first_text,
    optional_int,
)
from velvet_bot.infrastructure.media_delivery_repository_record import (
    MediaDeliveryRepositoryRecordMixin,
)

T = TypeVar("T")


class PostgresMediaDeliveryRepository(
    MediaDeliveryRepositoryRecordMixin,
    MediaDeliveryRepositoryBackfillMixin,
    MediaDeliveryRepositoryClaimMixin,
    MediaDeliveryRepositoryFinishMixin,
):
    """Translate database failures into the application delivery error contract."""

    def __init__(self, database: Database) -> None:
        super().__init__(database)

    async def _call(self, operation: str, awaitable: Awaitable[T]) -> T:
        try:
            return await awaitable
        except MediaDeliveryRepositoryError:
            raise
        except (
            asyncpg.PostgresError,
            OSError,
            TimeoutError,
            RuntimeError,
        ) as error:
            raise MediaDeliveryRepositoryError(operation, error) from error

    async def record_provider_submission(
        self,
        *,
        task_id: UUID,
        provider: str,
        provider_task_id: str,
        chat_id: int | None,
        media_kind: str,
        request: Mapping[str, object],
    ) -> None:
        await self._call(
            "record_provider_submission",
            super().record_provider_submission(
                task_id=task_id,
                provider=provider,
                provider_task_id=provider_task_id,
                chat_id=chat_id,
                media_kind=media_kind,
                request=request,
            ),
        )

    async def record_provider_success(
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
        await self._call(
            "record_provider_success",
            super().record_provider_success(
                task_id=task_id,
                provider=provider,
                provider_task_id=provider_task_id,
                chat_id=chat_id,
                media_kind=media_kind,
                request=request,
                result_urls=result_urls,
            ),
        )

    async def backfill_missing_successes(self, *, limit: int = 100) -> int:
        return await self._call(
            "backfill_missing_successes",
            super().backfill_missing_successes(limit=limit),
        )

    async def backfill_task(self, *, task_id: UUID) -> bool:
        return await self._call(
            "backfill_task",
            super().backfill_task(task_id=task_id),
        )

    async def claim_resolution(
        self,
        *,
        worker_id: str,
        task_id: UUID | None = None,
    ) -> MediaDeliveryJob | None:
        return await self._call(
            "claim_resolution",
            super().claim_resolution(worker_id=worker_id, task_id=task_id),
        )

    async def finish_resolution(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        error: BaseException | None,
        retry_delay_seconds: int | None,
        terminal: bool = False,
    ) -> None:
        await self._call(
            "finish_resolution",
            super().finish_resolution(
                task_id=task_id,
                worker_id=worker_id,
                error=error,
                retry_delay_seconds=retry_delay_seconds,
                terminal=terminal,
            ),
        )

    async def claim(
        self,
        *,
        worker_id: str,
        task_id: UUID | None = None,
    ) -> MediaDeliveryJob | None:
        return await self._call(
            "claim_delivery",
            super().claim(worker_id=worker_id, task_id=task_id),
        )

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
        await self._call(
            "mark_download",
            super().mark_download(
                task_id=task_id,
                result_index=result_index,
                status=status,
                error=error,
                content_type=content_type,
                file_name=file_name,
            ),
        )

    async def mark_channel(
        self,
        *,
        task_id: UUID,
        result_index: int,
        channel: str,
        status: MediaDeliveryStepStatus,
        error: BaseException | None = None,
    ) -> None:
        await self._call(
            f"mark_{channel}_{status.value}",
            super().mark_channel(
                task_id=task_id,
                result_index=result_index,
                channel=channel,
                status=status,
                error=error,
            ),
        )

    async def mark_notification(
        self,
        *,
        task_id: UUID,
        status: MediaDeliveryStepStatus,
        error: BaseException | None = None,
    ) -> None:
        await self._call(
            f"mark_notification_{status.value}",
            super().mark_notification(
                task_id=task_id,
                status=status,
                error=error,
            ),
        )

    async def finish(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        status: MediaDeliveryStatus,
        last_error: str | None,
        retry_delay_seconds: int | None,
    ) -> None:
        await self._call(
            "finish_delivery",
            super().finish(
                task_id=task_id,
                worker_id=worker_id,
                status=status,
                last_error=last_error,
                retry_delay_seconds=retry_delay_seconds,
            ),
        )

    async def reset_for_redelivery(self, *, task_id: UUID, chat_id: int) -> bool:
        return await self._call(
            "reset_for_redelivery",
            super().reset_for_redelivery(task_id=task_id, chat_id=chat_id),
        )


__all__ = (
    "PostgresMediaDeliveryRepository",
    "delivery_metadata",
    "first_text",
    "optional_int",
)
