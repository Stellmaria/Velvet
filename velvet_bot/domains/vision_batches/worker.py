from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import suppress
from functools import partial
from typing import Any
from uuid import UUID

from aiogram import Bot

from velvet_bot.ai_vision import VisionAnalysisError, VisionProviderUnavailable
from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.core.config import Settings
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import AITaskQueueService, AIUsageService
from velvet_bot.domains.telegram_storage.librarian_models import StorageLibrarianSettings
from velvet_bot.domains.telegram_storage.librarian_repository import (
    StorageLibrarianRepository,
)
from velvet_bot.domains.vision_batches.service import VISION_BATCH_TASK_TYPE
from velvet_bot.domains.vision_batches.store import VisionBatchRepository
from velvet_bot.domains.vision_routing import build_vision_cascade_router
from velvet_bot.domains.vision_routing.integration import (
    CascadeMediaAIRepository,
    CascadeMediaAIVisionService,
    VisionCascadeAdapter,
)
from velvet_bot.infrastructure.postgres.ai_task_wakeup_repository import (
    PostgresAITaskQueueDiagnostics,
)
from velvet_bot.local_ai_runtime import (
    get_local_ai_lock,
    storage_librarian_archive_phase_enabled,
)
from velvet_bot.workers.adaptive import (
    WorkerIterationOutcome,
    WorkerIterationResult,
)

logger = logging.getLogger(__name__)


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().casefold()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "да"}


async def storage_librarian_full_archive_has_priority(database: Database) -> bool:
    """Keep automatic VL behind the explicitly enabled Arthur full-archive phase."""

    runtime_archive = storage_librarian_archive_phase_enabled()
    legacy_archive = _env_enabled(
        "STORAGE_LIBRARIAN_AUTO_ENQUEUE", False
    ) and _env_enabled("STORAGE_LIBRARIAN_AUTO_BACKFILL", False)
    if not runtime_archive and not legacy_archive:
        return False

    try:
        settings = StorageLibrarianSettings.from_env()
    except ValueError as error:
        logger.error(
            "Storage Librarian priority gate failed closed on invalid configuration: %s",
            error,
        )
        return True
    if not settings.enabled:
        return False
    if not settings.allowed_kinds:
        logger.error("Storage Librarian priority gate failed closed: empty allowed_kinds")
        return True

    repository = StorageLibrarianRepository(database)
    counts = await repository.counts()
    if counts.get("running", 0) > 0 or counts.get("queued", 0) > 0:
        return True

    # Probe the exact existing full-archive eligibility query with a hard limit of
    # one. If work remains, queue exactly one Arthur item and keep VL closed. The
    # next gate iteration sees that queued/running item and cannot grow the queue
    # during either the legacy scheduler or Arthur's explicit archive idle interval.
    enqueued = await repository.enqueue_pending(settings=settings, limit=1)
    return enqueued > 0


class TargetedVisionService(CascadeMediaAIVisionService):
    def __init__(
        self,
        *,
        batch_repository: VisionBatchRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._batch_repository = batch_repository

    async def process_media_id(self, media_id: int) -> dict[str, object]:
        if not await self._provider_available():
            raise VisionProviderUnavailable("VL provider недоступен.")
        target = await self._batch_repository.claim_media_target(
            media_id=media_id,
            provider=self._client.provider,
            model=self._client.model,
            max_attempts=self._max_attempts,
        )
        if target is None:
            return {"media_id": media_id, "already_ready_or_unavailable": True}
        try:
            source = await self._download_target(target)
            profile = await self._client.analyze(source)
            await self._repository.mark_ready(media_id, profile)
            return {
                "media_id": media_id,
                "provider": str(getattr(profile, "provider", self._client.provider)),
                "model": str(getattr(profile, "model", self._client.model)),
                "route": str(getattr(profile, "route", "")),
                "cache_hit": bool(getattr(profile, "cache_hit", False)),
            }
        except asyncio.CancelledError:
            raise
        except BaseException as error:
            permanent = isinstance(error, VisionAnalysisError) and (
                "прочитать как изображение" in str(error)
                or "file is too big" in str(error).casefold()
            )
            await self._repository.mark_error(
                media_id,
                error,
                max_attempts=self._max_attempts,
                permanent=permanent,
            )
            raise


class VisionBatchQueueConsumer:
    def __init__(
        self,
        *,
        queue_service: AITaskQueueService,
        processor: TargetedVisionService,
        diagnostics: PostgresAITaskQueueDiagnostics | None = None,
        priority_gate: Callable[[], Awaitable[bool]] | None = None,
        local_ai_lock: asyncio.Lock | None = None,
        worker_id: str = "vision-semantic-batch",
        heartbeat_seconds: int = 60,
    ) -> None:
        self._queue = queue_service
        self._processor = processor
        self._diagnostics = diagnostics
        self._priority_gate = priority_gate
        self._local_ai_lock = local_ai_lock
        self._worker_id = worker_id
        self._heartbeat_seconds = max(15, int(heartbeat_seconds))

    async def _empty_result(self) -> WorkerIterationResult:
        oldest_age = (
            await self._diagnostics.oldest_queued_age_seconds()
            if self._diagnostics is not None
            else None
        )
        return WorkerIterationResult(
            WorkerIterationOutcome.EMPTY,
            oldest_queued_age_seconds=oldest_age,
        )

    async def process_once(self) -> WorkerIterationResult:
        if self._priority_gate is not None and await self._priority_gate():
            logger.info(
                "VL batch deferred: Storage Librarian full-archive has local inference priority"
            )
            return await self._empty_result()

        task = await self._queue.claim_next(
            worker_id=self._worker_id,
            scopes=(AIBudgetScope.VISION,),
            task_types=(VISION_BATCH_TASK_TYPE,),
        )
        if task is None:
            return await self._empty_result()
        heartbeat = asyncio.create_task(self._heartbeat(task.id))
        try:
            media_id = int(task.payload.get("media_id") or 0)
            if media_id <= 0:
                raise ValueError("AI-задача не содержит корректный media_id.")
            if self._local_ai_lock is None:
                result = await self._processor.process_media_id(media_id)
            else:
                async with self._local_ai_lock:
                    result = await self._processor.process_media_id(media_id)
            completed = await self._queue.complete(
                task_id=task.id,
                worker_id=self._worker_id,
                result=result,
            )
            if completed is None:
                logger.warning(
                    "VL batch task lost lock before completion task_id=%s",
                    task.id,
                )
                return WorkerIterationResult(WorkerIterationOutcome.SKIPPED)
            return WorkerIterationResult(
                WorkerIterationOutcome.PROCESSED,
                processed_items=1,
            )
        except asyncio.CancelledError:
            raise
        except BaseException as error:
            failure = await self._queue.fail(
                task_id=task.id,
                worker_id=self._worker_id,
                error=error,
            )
            logger.warning(
                "VL batch task failed task_id=%s media_id=%s: %s",
                task.id,
                task.payload.get("media_id"),
                error,
            )
            outcome = (
                WorkerIterationOutcome.TRANSIENT_FAILURE
                if failure is not None and failure.will_retry
                else WorkerIterationOutcome.TERMINAL_FAILURE
            )
            return WorkerIterationResult(outcome)
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def _heartbeat(self, task_id: UUID) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_seconds)
            updated = await self._queue.heartbeat(
                task_id=task_id,
                worker_id=self._worker_id,
            )
            if not updated:
                return


def build_vision_batch_consumer(
    *,
    bot: Bot,
    database: Database,
    settings: Settings,
    usage_service: AIUsageService,
    queue_service: AITaskQueueService,
    cache_chat_id: int | None,
) -> VisionBatchQueueConsumer:
    router = build_vision_cascade_router(
        settings=settings,
        database=database,
        ai_usage_service=usage_service,
    )
    batch_repository = VisionBatchRepository(database)
    processor = TargetedVisionService(
        bot=bot,
        repository=CascadeMediaAIRepository(database),
        client=VisionCascadeAdapter(router),
        max_attempts=settings.ai_vision_max_attempts,
        batch_repository=batch_repository,
    )
    processor.set_cache_chat_id(cache_chat_id)
    return VisionBatchQueueConsumer(
        queue_service=queue_service,
        processor=processor,
        diagnostics=PostgresAITaskQueueDiagnostics(database),
        priority_gate=partial(storage_librarian_full_archive_has_priority, database),
        local_ai_lock=get_local_ai_lock(),
    )


__all__ = (
    "TargetedVisionService",
    "VisionBatchQueueConsumer",
    "build_vision_batch_consumer",
)
