from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from uuid import UUID

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import (
    AITask,
    AITaskFailureResult,
    AITaskQueueService,
    AITaskRepository,
)


class KieTaskQueueService(AITaskQueueService):
    """AI task queue view that owns the Kie campaign retry contract."""

    def __init__(
        self,
        *,
        database: Database,
        max_attempts: int = 50,
    ) -> None:
        super().__init__(AITaskRepository(database))
        self._database = database
        self._max_attempts = max(1, min(50, int(max_attempts)))

    async def claim_next(
        self,
        *,
        worker_id: str,
        scopes: tuple[AIBudgetScope, ...] | None = None,
        task_types: tuple[str, ...] | None = None,
    ) -> AITask | None:
        task = await super().claim_next(
            worker_id=worker_id,
            scopes=scopes,
            task_types=task_types,
        )
        if task is None or task.max_attempts >= self._max_attempts:
            return task

        async with self._database.acquire() as connection:
            result = await connection.execute(
                """UPDATE ai_tasks
                   SET max_attempts=GREATEST(max_attempts,$2::INTEGER),updated_at=NOW()
                   WHERE id=$1::UUID AND status='running' AND locked_by=$3::VARCHAR""",
                task.id,
                self._max_attempts,
                worker_id.strip(),
            )
        if not result.endswith(" 1"):
            return task
        return replace(task, max_attempts=self._max_attempts)

    async def patch_payload(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        patch: Mapping[str, object],
    ) -> bool:
        """Persist campaign state while retaining ownership of the running task."""

        if not patch:
            return True
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """UPDATE ai_tasks
                   SET payload=payload || $3::JSONB,updated_at=NOW(),locked_at=NOW()
                   WHERE id=$1::UUID AND status='running' AND locked_by=$2::VARCHAR""",
                task_id,
                worker_id.strip(),
                json.dumps(dict(patch), ensure_ascii=False, default=str),
            )
        return result.endswith(" 1")

    async def fail_terminal(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        error: BaseException,
    ) -> AITaskFailureResult | None:
        """Finish a permanent or financially ambiguous failure without retrying."""

        normalized_worker = worker_id.strip()
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """UPDATE ai_tasks
                   SET max_attempts=GREATEST(1,attempt_count),updated_at=NOW()
                   WHERE id=$1::UUID AND status='running' AND locked_by=$2::VARCHAR""",
                task_id,
                normalized_worker,
            )
        if not result.endswith(" 1"):
            return None
        return await super().fail(
            task_id=task_id,
            worker_id=normalized_worker,
            error=error,
            base_delay_seconds=0,
            max_delay_seconds=0,
        )


__all__ = ("KieTaskQueueService",)
