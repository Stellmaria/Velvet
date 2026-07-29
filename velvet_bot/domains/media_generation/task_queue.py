from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import AITask, AITaskQueueService, AITaskRepository


class KieTaskQueueService(AITaskQueueService):
    """AI task queue view that enforces the Kie retry budget on claim."""

    def __init__(
        self,
        *,
        database: Database,
        max_attempts: int = 11,
    ) -> None:
        super().__init__(AITaskRepository(database))
        self._database = database
        self._max_attempts = max(1, min(20, int(max_attempts)))

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


__all__ = ("KieTaskQueueService",)
