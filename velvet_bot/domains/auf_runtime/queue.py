from __future__ import annotations

from uuid import UUID

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import AITask, AITaskFailureResult
from velvet_bot.domains.ai_usage.tasks import _columns, _task_from_row, _worker_id
from velvet_bot.domains.media_generation.models import KIE_GENERATION_TASK_TYPE
from velvet_bot.domains.media_generation.task_queue import KieTaskQueueService
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.infrastructure.ai import KieTaskFailed

from .models import AufProvider


class ProviderAufTaskQueueService(KieTaskQueueService):
    """Claim media jobs for one provider while enforcing workspace concurrency."""

    def __init__(self, *, database, provider: AufProvider, max_attempts: int = 50) -> None:
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
                       CROSS JOIN meow_runtime_settings AS auf_runtime
                       WHERE runtime.singleton_id = 1
                         AND auf_runtime.singleton_id = 1
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
                                      auf_runtime.workspace_default_limit
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

    async def eligible_count(self) -> int:
        """Count queued jobs that can start now after workspace quotas."""

        aliases = list(self.provider.model_aliases)
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                WITH running_by_workspace AS (
                    SELECT
                        NULLIF(payload->>'workspace_id', '')::BIGINT AS workspace_id,
                        COUNT(*) AS running_count
                    FROM ai_tasks
                    WHERE status = 'running'
                      AND task_type = $1::VARCHAR
                      AND created_by <> $3::BIGINT
                    GROUP BY NULLIF(payload->>'workspace_id', '')::BIGINT
                ),
                ranked_workspace AS (
                    SELECT
                        ROW_NUMBER() OVER (
                            PARTITION BY NULLIF(
                                task.payload->>'workspace_id',
                                ''
                            )::BIGINT
                            ORDER BY task.priority ASC,
                                     task.not_before ASC,
                                     task.created_at ASC,
                                     task.id ASC
                        ) AS workspace_position,
                        COALESCE(
                            workspace_limit.concurrency_limit,
                            runtime.workspace_default_limit
                        ) AS concurrency_limit,
                        COALESCE(running.running_count, 0) AS running_count
                    FROM ai_tasks AS task
                    CROSS JOIN meow_runtime_settings AS runtime
                    LEFT JOIN workspace_meow_settings AS workspace_limit
                      ON workspace_limit.workspace_id =
                         NULLIF(task.payload->>'workspace_id', '')::BIGINT
                    LEFT JOIN running_by_workspace AS running
                      ON running.workspace_id =
                         NULLIF(task.payload->>'workspace_id', '')::BIGINT
                    WHERE runtime.singleton_id = 1
                      AND task.status = 'queued'
                      AND task.not_before <= NOW()
                      AND task.task_type = $1::VARCHAR
                      AND task.created_by <> $3::BIGINT
                      AND task.payload->'request'->>'model' = ANY($2::VARCHAR[])
                ),
                workspace_eligible AS (
                    SELECT COUNT(*) AS total
                    FROM ranked_workspace
                    WHERE workspace_position <= GREATEST(
                        concurrency_limit - running_count,
                        0
                    )
                ),
                stell_eligible AS (
                    SELECT COUNT(*) AS total
                    FROM ai_tasks
                    WHERE status = 'queued'
                      AND not_before <= NOW()
                      AND task_type = $1::VARCHAR
                      AND created_by = $3::BIGINT
                      AND payload->'request'->>'model' = ANY($2::VARCHAR[])
                )
                SELECT workspace_eligible.total + stell_eligible.total
                FROM workspace_eligible, stell_eligible
                """,
                KIE_GENERATION_TASK_TYPE,
                aliases,
                GLOBAL_WORKSPACE_CREATOR_ID,
            )
        return int(value or 0)

    async def cancellation_requested(self, *, task_id: UUID) -> bool:
        requested, _ = await self._cancellation_state(task_id=task_id)
        return requested

    async def _cancellation_state(self, *, task_id: UUID) -> tuple[bool, bool]:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    COALESCE((payload->>'cancel_requested')::BOOLEAN, FALSE)
                        AS cancel_requested,
                    COALESCE(
                        NULLIF(
                            payload->'kie_campaign'->>'active_provider_task_id',
                            ''
                        ) IS NOT NULL,
                        FALSE
                    ) AS provider_started
                FROM ai_tasks
                WHERE id = $1::UUID
                """,
                task_id,
            )
        if row is None:
            return False, False
        return bool(row["cancel_requested"]), bool(row["provider_started"])

    async def fail(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        error: BaseException,
        base_delay_seconds: int = 30,
        max_delay_seconds: int = 3600,
    ) -> AITaskFailureResult | None:
        cancel_requested, provider_started = await self._cancellation_state(
            task_id=task_id
        )
        should_finish_cancelled = cancel_requested and (
            not provider_started or isinstance(error, KieTaskFailed)
        )
        if should_finish_cancelled:
            if provider_started:
                reason = (
                    "Пользователь запросил остановку. Уже отправленная provider-задача "
                    "завершилась ошибкой; новая платная попытка не запускается."
                )
            else:
                reason = (
                    "Пользователь отменил задачу до получения provider task id; "
                    "подготовка или отправка завершилась ошибкой, повтор не запускается."
                )
            cancelled = await self.finish_cancelled(
                task_id=task_id,
                worker_id=worker_id,
                reason=reason,
            )
            if cancelled is None:
                return None
            return AITaskFailureResult(
                task=cancelled,
                will_retry=False,
                retry_delay_seconds=None,
            )
        return await super().fail(
            task_id=task_id,
            worker_id=worker_id,
            error=error,
            base_delay_seconds=base_delay_seconds,
            max_delay_seconds=max_delay_seconds,
        )

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


__all__ = ("ProviderAufTaskQueueService",)
