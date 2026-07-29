from __future__ import annotations

from uuid import UUID

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import AITask
from velvet_bot.domains.ai_usage.tasks import _columns, _task_from_row, _worker_id
from velvet_bot.domains.media_generation.models import KIE_GENERATION_TASK_TYPE
from velvet_bot.domains.media_generation.task_queue import KieTaskQueueService
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID

from .models import MeowProvider


class ProviderMeowTaskQueueService(KieTaskQueueService):
    """Claim media jobs for one provider while enforcing workspace concurrency."""

    def __init__(self, *, database, provider: MeowProvider, max_attempts: int = 50) -> None:
        super().__init__(database=database, max_attempts=max_attempts)
        self.provider = provider

    async def claim_next(
        self,
        *,
        worker_id: str,
        scopes: tuple[AIBudgetScope, ...] | None = None,
        task_types: tuple[str, ...] | None = None,
    ) -> AITask | None:
        del scopes, task_types
        normalized_worker = _worker_id(worker_id)
        aliases = list(self.provider.model_aliases)
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                f"""WITH candidate AS (
                       SELECT task.id
                       FROM ai_tasks AS task
                       CROSS JOIN ai_runtime_state AS runtime
                       LEFT JOIN workspace_meow_settings AS workspace_limit
                         ON workspace_limit.workspace_id =
                            NULLIF(task.payload->>'workspace_id', '')::BIGINT
                       CROSS JOIN meow_runtime_settings AS meow_runtime
                       WHERE runtime.singleton_id = 1
                         AND meow_runtime.singleton_id = 1
                         AND runtime.paused = FALSE
                         AND task.status = 'queued'
                         AND task.not_before <= NOW()
                         AND task.task_type = $2::VARCHAR
                         AND task.payload->'request'->>'model' = ANY($3::VARCHAR[])
                         AND (
                              task.created_by = $4::BIGINT
                              OR (
                                  pg_try_advisory_xact_lock(
                                      NULLIF(task.payload->>'workspace_id', '')::BIGINT
                                  )
                                  AND (
                                      SELECT COUNT(*)
                                      FROM ai_tasks AS running
                                      WHERE running.status = 'running'
                                        AND running.task_type = $2::VARCHAR
                                        AND running.created_by <> $4::BIGINT
                                        AND NULLIF(running.payload->>'workspace_id', '')::BIGINT =
                                            NULLIF(task.payload->>'workspace_id', '')::BIGINT
                                  ) < COALESCE(
                                      workspace_limit.concurrency_limit,
                                      meow_runtime.workspace_default_limit
                                  )
                              )
                         )
                       ORDER BY
                           CASE WHEN task.created_by = $4::BIGINT THEN 0 ELSE 1 END,
                           task.priority ASC,
                           task.not_before ASC,
                           task.created_at ASC
                       FOR UPDATE OF task SKIP LOCKED
                       LIMIT 1
                   )
                   UPDATE ai_tasks AS task
                   SET status = 'running',
                       attempt_count = task.attempt_count + 1,
                       max_attempts = GREATEST(task.max_attempts, $5::INTEGER),
                       locked_by = $1::VARCHAR,
                       locked_at = NOW(),
                       updated_at = NOW(),
                       last_error_type = NULL,
                       last_error = NULL,
                       last_retry_delay_seconds = NULL,
                       completed_at = NULL
                   FROM candidate
                   WHERE task.id = candidate.id
                   RETURNING {_columns('task')}""",
                normalized_worker,
                KIE_GENERATION_TASK_TYPE,
                aliases,
                GLOBAL_WORKSPACE_CREATOR_ID,
                self._max_attempts,
            )
        return _task_from_row(row) if row is not None else None

    async def running_count(self) -> int:
        aliases = list(self.provider.model_aliases)
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM ai_tasks
                WHERE status = 'running'
                  AND task_type = $1::VARCHAR
                  AND payload->'request'->>'model' = ANY($2::VARCHAR[])
                """,
                KIE_GENERATION_TASK_TYPE,
                aliases,
            )
        return int(value or 0)

    async def queued_count(self) -> int:
        aliases = list(self.provider.model_aliases)
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM ai_tasks
                WHERE status = 'queued'
                  AND not_before <= NOW()
                  AND task_type = $1::VARCHAR
                  AND payload->'request'->>'model' = ANY($2::VARCHAR[])
                """,
                KIE_GENERATION_TASK_TYPE,
                aliases,
            )
        return int(value or 0)

    async def cancellation_requested(self, *, task_id: UUID) -> bool:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT COALESCE((payload->>'cancel_requested')::BOOLEAN, FALSE)
                FROM ai_tasks
                WHERE id = $1::UUID
                """,
                task_id,
            )
        return bool(value)

    async def finish_cancelled(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        reason: str,
    ) -> AITask | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                UPDATE ai_tasks
                SET status = 'cancelled',
                    locked_by = NULL,
                    locked_at = NULL,
                    last_error_type = 'CancelledByUser',
                    last_error = $3::TEXT,
                    last_retry_delay_seconds = NULL,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1::UUID
                  AND status = 'running'
                  AND locked_by = $2::VARCHAR
                RETURNING {_columns()}
                """,
                task_id,
                _worker_id(worker_id),
                reason.strip()[:8000] or "Cancelled by user.",
            )
        return _task_from_row(row) if row is not None else None


__all__ = ("ProviderMeowTaskQueueService",)
