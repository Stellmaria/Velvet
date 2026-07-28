from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from uuid import UUID

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage.task_models import (
    AITask,
    AITaskEnqueueResult,
    AITaskFailureResult,
    AITaskQueueSnapshot,
    AITaskRequest,
)
from velvet_bot.domains.ai_usage.tasks import AITaskRepository


class AITaskQueueService:
    def __init__(self, repository: AITaskRepository) -> None:
        self._repository = repository

    async def enqueue(self, request: AITaskRequest) -> AITaskEnqueueResult:
        return await self._repository.enqueue(request)

    async def enqueue_many(
        self,
        requests: Sequence[AITaskRequest],
    ) -> tuple[AITaskEnqueueResult, ...]:
        return await self._repository.enqueue_many(requests)

    async def claim_next(
        self,
        *,
        worker_id: str,
        scopes: Sequence[AIBudgetScope] | None = None,
        task_types: Sequence[str] | None = None,
    ) -> AITask | None:
        return await self._repository.claim_next(
            worker_id=worker_id,
            scopes=scopes,
            task_types=task_types,
        )

    async def heartbeat(self, *, task_id: UUID, worker_id: str) -> bool:
        return await self._repository.heartbeat(
            task_id=task_id,
            worker_id=worker_id,
        )

    async def complete(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        result: Mapping[str, object] | None = None,
    ) -> AITask | None:
        return await self._repository.complete(
            task_id=task_id,
            worker_id=worker_id,
            result=result,
        )

    async def fail(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        error: BaseException,
        base_delay_seconds: int = 30,
        max_delay_seconds: int = 3600,
    ) -> AITaskFailureResult | None:
        return await self._repository.fail(
            task_id=task_id,
            worker_id=worker_id,
            error=error,
            base_delay_seconds=base_delay_seconds,
            max_delay_seconds=max_delay_seconds,
        )

    async def cancel(self, *, task_id: UUID, reason: str) -> AITask | None:
        return await self._repository.cancel(task_id=task_id, reason=reason)

    async def requeue(self, *, task_id: UUID) -> AITask | None:
        return await self._repository.requeue(task_id=task_id)

    async def recover_stale(
        self,
        *,
        older_than: datetime,
        limit: int = 100,
    ) -> tuple[AITask, ...]:
        return await self._repository.recover_stale(
            older_than=older_than,
            limit=limit,
        )

    async def recover_expired_locks(
        self,
        *,
        stale_after_seconds: int = 900,
        limit: int = 100,
    ) -> tuple[AITask, ...]:
        threshold = datetime.now(timezone.utc) - timedelta(
            seconds=max(30, int(stale_after_seconds))
        )
        return await self.recover_stale(older_than=threshold, limit=limit)

    async def snapshot(self) -> AITaskQueueSnapshot:
        return await self._repository.snapshot()

    async def recent(self, *, limit: int = 20) -> tuple[AITask, ...]:
        return await self._repository.recent(limit=limit)

    async def get(self, *, task_id: UUID) -> AITask | None:
        return await self._repository.get(task_id=task_id)


__all__ = ("AITaskQueueService",)
