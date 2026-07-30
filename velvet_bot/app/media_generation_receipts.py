from __future__ import annotations

import time

from velvet_bot.domains.ai_usage import AITask
from velvet_bot.domains.media_generation.friendly_worker import FriendlyKieGenerationWorker
from velvet_bot.domains.media_generation.models import KieGenerationRequest

from .media_generation_receipt_core import (
    ReceiptContext as _ReceiptContext,
    aggregate_delivery_status as _aggregate_delivery_status,
    duration_text as _duration_text,
    extract_attempt as _extract_attempt,
    extract_consumed_credits as _extract_consumed_credits,
    extract_provider_task_id as _extract_provider_task_id,
    provider_latency_ms as _provider_latency_ms,
)
from .media_generation_receipt_delivery import deliver_with_receipt as _deliver_with_receipt

_INSTALLED = False
_ORIGINAL_START_PROGRESS = FriendlyKieGenerationWorker._start_progress
_ORIGINAL_PUBLISH_PROGRESS = FriendlyKieGenerationWorker._publish_progress


def _worker_contexts(
    worker: FriendlyKieGenerationWorker,
) -> tuple[dict[str, _ReceiptContext], dict[str, _ReceiptContext]]:
    by_queue = getattr(worker, "_media_receipt_by_queue", None)
    if not isinstance(by_queue, dict):
        by_queue = {}
        setattr(worker, "_media_receipt_by_queue", by_queue)
    by_provider = getattr(worker, "_media_receipt_by_provider", None)
    if not isinstance(by_provider, dict):
        by_provider = {}
        setattr(worker, "_media_receipt_by_provider", by_provider)
    return by_queue, by_provider


async def _start_progress_with_receipt(
    self: FriendlyKieGenerationWorker,
    *,
    task: AITask,
    request: KieGenerationRequest,
):
    by_queue, _ = _worker_contexts(self)
    by_queue[str(task.id)] = _ReceiptContext(
        task=task,
        request=request,
        started_monotonic=time.monotonic(),
        max_attempts=max(1, int(task.max_attempts)),
    )
    return await _ORIGINAL_START_PROGRESS(self, task=task, request=request)


async def _publish_progress_with_receipt(
    self: FriendlyKieGenerationWorker,
    progress,
    *,
    task: AITask,
    request: KieGenerationRequest,
    percent: int,
    stage: str,
    force: bool = False,
) -> None:
    by_queue, by_provider = _worker_contexts(self)
    context = by_queue.setdefault(
        str(task.id),
        _ReceiptContext(
            task=task,
            request=request,
            started_monotonic=time.monotonic(),
            max_attempts=max(1, int(task.max_attempts)),
        ),
    )
    attempt = _extract_attempt(stage)
    if attempt is not None:
        context.provider_attempt, context.max_attempts = attempt
    provider_task_id = _extract_provider_task_id(stage)
    if provider_task_id is not None:
        context.provider_task_id = provider_task_id
        context.provider_started_monotonic = context.provider_started_monotonic or time.monotonic()
        by_provider[provider_task_id] = context
    await _ORIGINAL_PUBLISH_PROGRESS(
        self,
        progress,
        task=task,
        request=request,
        percent=percent,
        stage=stage,
        force=force,
    )


def install_media_generation_receipts() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    FriendlyKieGenerationWorker._start_progress = _start_progress_with_receipt
    FriendlyKieGenerationWorker._publish_progress = _publish_progress_with_receipt
    FriendlyKieGenerationWorker._deliver_best_effort = _deliver_with_receipt
    _INSTALLED = True


__all__ = ("install_media_generation_receipts",)
