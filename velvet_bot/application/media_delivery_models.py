from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Protocol
from uuid import UUID

class MediaDeliveryStatus(StrEnum):
    PROVIDER_SUBMITTED = 'provider_submitted'
    PROVIDER_SUCCESS = 'provider_success'
    RESULT_RESOLVED = 'result_resolved'
    DELIVERING = 'delivering'
    RETRY = 'retry'
    DELIVERED = 'delivered'
    PARTIAL = 'partial'
    EXPIRED = 'expired'
    FAILED = 'failed'

class MediaDeliveryStepStatus(StrEnum):
    PENDING = 'pending'
    SUCCESS = 'success'
    FAILED = 'failed'
    EXPIRED = 'expired'
    SKIPPED = 'skipped'

@dataclass(frozen=True, slots=True)
class MediaDeliveryItem:
    result_index: int
    result_url: str
    url_status: str
    download_status: MediaDeliveryStepStatus
    original_status: MediaDeliveryStepStatus
    preview_status: MediaDeliveryStepStatus
    content_type: str | None = None
    file_name: str | None = None

@dataclass(frozen=True, slots=True)
class MediaDeliveryJob:
    task_id: UUID
    provider: str
    provider_task_id: str
    chat_id: int | None
    media_kind: str
    request: Mapping[str, object]
    status: MediaDeliveryStatus
    attempt_count: int
    notification_status: MediaDeliveryStepStatus
    items: tuple[MediaDeliveryItem, ...]

@dataclass(frozen=True, slots=True)
class DownloadedMedia:
    payload: bytes
    file_name: str
    content_type: str | None

@dataclass(frozen=True, slots=True)
class MediaDeliverySummary:
    task_id: UUID
    status: MediaDeliveryStatus
    item_count: int
    original_sent: int
    preview_sent: int
    expired_items: int
    retry_scheduled: bool

class MediaUrlExpired(RuntimeError):
    """The provider URL is known to be permanently unusable."""

class ProviderResultResolver(Protocol):

    async def resolve(self, *, provider: str, provider_task_id: str) -> tuple[str, ...]:
        ...

class MediaDeliveryRepository(Protocol):

    async def record_provider_submission(self, *, task_id: UUID, provider: str, provider_task_id: str, chat_id: int | None, media_kind: str, request: Mapping[str, object]) -> None:
        ...

    async def record_provider_success(self, *, task_id: UUID, provider: str, provider_task_id: str, chat_id: int | None, media_kind: str, request: Mapping[str, object], result_urls: tuple[str, ...]) -> None:
        ...

    async def backfill_missing_successes(self, *, limit: int=100) -> int:
        ...

    async def backfill_task(self, *, task_id: UUID) -> bool:
        ...

    async def claim_resolution(self, *, worker_id: str, task_id: UUID | None=None) -> MediaDeliveryJob | None:
        ...

    async def finish_resolution(self, *, task_id: UUID, worker_id: str, error: BaseException | None, retry_delay_seconds: int | None, terminal: bool=False) -> None:
        ...

    async def claim(self, *, worker_id: str, task_id: UUID | None=None) -> MediaDeliveryJob | None:
        ...

    async def mark_download(self, *, task_id: UUID, result_index: int, status: MediaDeliveryStepStatus, error: BaseException | None=None, content_type: str | None=None, file_name: str | None=None) -> None:
        ...

    async def mark_channel(self, *, task_id: UUID, result_index: int, channel: str, status: MediaDeliveryStepStatus, error: BaseException | None=None) -> None:
        ...

    async def mark_notification(self, *, task_id: UUID, status: MediaDeliveryStepStatus, error: BaseException | None=None) -> None:
        ...

    async def finish(self, *, task_id: UUID, worker_id: str, status: MediaDeliveryStatus, last_error: str | None, retry_delay_seconds: int | None) -> None:
        ...

    async def reset_for_redelivery(self, *, task_id: UUID, chat_id: int) -> bool:
        ...

class MediaDeliveryTransport(Protocol):

    async def download(self, *, job: MediaDeliveryJob, item: MediaDeliveryItem) -> DownloadedMedia:
        ...

    async def send_original(self, *, job: MediaDeliveryJob, item: MediaDeliveryItem, media: DownloadedMedia) -> None:
        ...

    async def send_preview(self, *, job: MediaDeliveryJob, item: MediaDeliveryItem, media: DownloadedMedia) -> None:
        ...

    async def send_direct_preview(self, *, job: MediaDeliveryJob, item: MediaDeliveryItem) -> None:
        ...

    async def notify(self, *, job: MediaDeliveryJob, text: str) -> None:
        ...

__all__ = ("DownloadedMedia", "MediaDeliveryItem", "MediaDeliveryJob", "MediaDeliveryRepository", "MediaDeliveryStatus", "MediaDeliveryStepStatus", "MediaDeliverySummary", "MediaDeliveryTransport", "MediaUrlExpired", "ProviderResultResolver")
