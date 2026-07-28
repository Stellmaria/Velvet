from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage.task_models import (
    AITask,
    AITaskEnqueueResult,
    AITaskFailureResult,
    AITaskQueueSnapshot,
    AITaskRequest,
    AITaskStatus,
)

_TASK_FIELDS = (
    "id",
    "scope",
    "task_type",
    "status",
    "priority",
    "payload",
    "result",
    "dedupe_key",
    "attempt_count",
    "max_attempts",
    "not_before",
    "locked_by",
    "locked_at",
    "last_error_type",
    "last_error",
    "last_retry_delay_seconds",
    "estimated_cost_rub",
    "created_by",
    "created_at",
    "updated_at",
    "completed_at",
)


def _columns(alias: str | None = None) -> str:
    prefix = f"{alias}." if alias else ""
    return ",".join(f"{prefix}{field}" for field in _TASK_FIELDS)


class AITaskRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def enqueue(self, request: AITaskRequest) -> AITaskEnqueueResult:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                return await self._enqueue_on_connection(connection, request)

    async def enqueue_many(
        self,
        requests: Sequence[AITaskRequest],
    ) -> tuple[AITaskEnqueueResult, ...]:
        if not requests:
            return ()
        async with self._database.acquire() as connection:
            async with connection.transaction():
                return tuple(
                    [
                        await self._enqueue_on_connection(connection, request)
                        for request in requests
                    ]
                )

    async def claim_next(
        self,
        *,
        worker_id: str,
        scopes: Sequence[AIBudgetScope] | None = None,
        task_types: Sequence[str] | None = None,
    ) -> AITask | None:
        normalized_worker = _worker_id(worker_id)
        scope_values = (
            [scope.value for scope in scopes]
            if scopes is not None
            else None
        )
        type_values = (
            [value.strip() for value in task_types if value.strip()]
            if task_types is not None
            else None
        )
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                f"""WITH candidate AS (
                       SELECT task.id
                       FROM ai_tasks AS task
                       CROSS JOIN ai_runtime_state AS runtime
                       WHERE runtime.singleton_id=1
                         AND runtime.paused=FALSE
                         AND task.status='queued'
                         AND task.not_before<=NOW()
                         AND ($2::VARCHAR[] IS NULL OR task.scope=ANY($2::VARCHAR[]))
                         AND ($3::VARCHAR[] IS NULL OR task.task_type=ANY($3::VARCHAR[]))
                       ORDER BY task.priority ASC,task.not_before ASC,task.created_at ASC
                       FOR UPDATE OF task SKIP LOCKED
                       LIMIT 1
                   )
                   UPDATE ai_tasks AS task
                   SET status='running',attempt_count=task.attempt_count+1,
                       locked_by=$1::VARCHAR,locked_at=NOW(),updated_at=NOW(),
                       last_error_type=NULL,last_error=NULL,
                       last_retry_delay_seconds=NULL,completed_at=NULL
                   FROM candidate
                   WHERE task.id=candidate.id
                   RETURNING {_columns('task')}""",
                normalized_worker,
                scope_values,
                type_values,
            )
        return _task_from_row(row) if row is not None else None

    async def heartbeat(self, *, task_id: UUID, worker_id: str) -> bool:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """UPDATE ai_tasks
                   SET locked_at=NOW(),updated_at=NOW()
                   WHERE id=$1::UUID AND status='running' AND locked_by=$2::VARCHAR""",
                task_id,
                _worker_id(worker_id),
            )
        return result.endswith(" 1")

    async def complete(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        result: Mapping[str, object] | None = None,
    ) -> AITask | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                f"""UPDATE ai_tasks
                   SET status='success',result=$3::JSONB,locked_by=NULL,locked_at=NULL,
                       last_error_type=NULL,last_error=NULL,
                       last_retry_delay_seconds=NULL,completed_at=NOW(),updated_at=NOW()
                   WHERE id=$1::UUID AND status='running' AND locked_by=$2::VARCHAR
                   RETURNING {_columns()}""",
                task_id,
                _worker_id(worker_id),
                json.dumps(dict(result or {}), ensure_ascii=False, default=str),
            )
        return _task_from_row(row) if row is not None else None

    async def fail(
        self,
        *,
        task_id: UUID,
        worker_id: str,
        error: BaseException,
        base_delay_seconds: int = 30,
        max_delay_seconds: int = 3600,
    ) -> AITaskFailureResult | None:
        base_delay = max(0, int(base_delay_seconds))
        max_delay = max(base_delay, int(max_delay_seconds))
        normalized_worker = _worker_id(worker_id)
        async with self._database.acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    f"""SELECT {_columns()}
                       FROM ai_tasks
                       WHERE id=$1::UUID AND status='running' AND locked_by=$2::VARCHAR
                       FOR UPDATE""",
                    task_id,
                    normalized_worker,
                )
                if current is None:
                    return None
                attempt_count = int(current["attempt_count"])
                max_attempts = int(current["max_attempts"])
                error_type = type(error).__name__[:160]
                error_message = str(error)[:8000]
                if attempt_count < max_attempts:
                    delay = min(
                        max_delay,
                        base_delay * (2 ** max(0, attempt_count - 1)),
                    )
                    row = await connection.fetchrow(
                        f"""UPDATE ai_tasks
                           SET status='queued',not_before=NOW()+($3::INTEGER*INTERVAL '1 second'),
                               locked_by=NULL,locked_at=NULL,last_error_type=$4::VARCHAR,
                               last_error=$5::TEXT,last_retry_delay_seconds=$3::INTEGER,
                               completed_at=NULL,updated_at=NOW()
                           WHERE id=$1::UUID AND status='running' AND locked_by=$2::VARCHAR
                           RETURNING {_columns()}""",
                        task_id,
                        normalized_worker,
                        delay,
                        error_type,
                        error_message,
                    )
                    if row is None:
                        return None
                    return AITaskFailureResult(
                        task=_task_from_row(row),
                        will_retry=True,
                        retry_delay_seconds=delay,
                    )

                row = await connection.fetchrow(
                    f"""UPDATE ai_tasks
                       SET status='error',locked_by=NULL,locked_at=NULL,
                           last_error_type=$3::VARCHAR,last_error=$4::TEXT,
                           last_retry_delay_seconds=NULL,completed_at=NOW(),updated_at=NOW()
                       WHERE id=$1::UUID AND status='running' AND locked_by=$2::VARCHAR
                       RETURNING {_columns()}""",
                    task_id,
                    normalized_worker,
                    error_type,
                    error_message,
                )
                if row is None:
                    return None
                return AITaskFailureResult(
                    task=_task_from_row(row),
                    will_retry=False,
                    retry_delay_seconds=None,
                )

    async def cancel(self, *, task_id: UUID, reason: str) -> AITask | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                f"""UPDATE ai_tasks
                   SET status='cancelled',locked_by=NULL,locked_at=NULL,
                       last_error_type='CancelledByOwner',last_error=$2::TEXT,
                       last_retry_delay_seconds=NULL,completed_at=NOW(),updated_at=NOW()
                   WHERE id=$1::UUID AND status IN ('queued','running')
                   RETURNING {_columns()}""",
                task_id,
                reason.strip()[:8000] or "Cancelled by owner.",
            )
        return _task_from_row(row) if row is not None else None

    async def requeue(self, *, task_id: UUID) -> AITask | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                f"""UPDATE ai_tasks
                   SET status='queued',attempt_count=0,not_before=NOW(),
                       locked_by=NULL,locked_at=NULL,result='{{}}'::JSONB,
                       last_error_type=NULL,last_error=NULL,
                       last_retry_delay_seconds=NULL,completed_at=NULL,updated_at=NOW()
                   WHERE id=$1::UUID AND status IN ('error','cancelled')
                   RETURNING {_columns()}""",
                task_id,
            )
        return _task_from_row(row) if row is not None else None

    async def recover_stale(
        self,
        *,
        older_than: datetime,
        limit: int = 100,
    ) -> tuple[AITask, ...]:
        safe_limit = max(1, min(int(limit), 1000))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                f"""WITH stale AS (
                       SELECT stale_task.id
                       FROM ai_tasks AS stale_task
                       WHERE stale_task.status='running'
                         AND stale_task.locked_at<$1::TIMESTAMPTZ
                       ORDER BY stale_task.locked_at ASC
                       FOR UPDATE OF stale_task SKIP LOCKED
                       LIMIT $2::INTEGER
                   )
                   UPDATE ai_tasks AS task
                   SET status=CASE
                           WHEN task.attempt_count<task.max_attempts THEN 'queued'
                           ELSE 'error'
                       END,
                       not_before=CASE
                           WHEN task.attempt_count<task.max_attempts THEN NOW()
                           ELSE task.not_before
                       END,
                       locked_by=NULL,locked_at=NULL,
                       last_error_type='StaleTaskLock',
                       last_error='Worker lock expired before task completion.',
                       last_retry_delay_seconds=CASE
                           WHEN task.attempt_count<task.max_attempts THEN 0
                           ELSE NULL
                       END,
                       completed_at=CASE
                           WHEN task.attempt_count<task.max_attempts THEN NULL
                           ELSE NOW()
                       END,
                       updated_at=NOW()
                   FROM stale
                   WHERE task.id=stale.id
                   RETURNING {_columns('task')}""",
                older_than,
                safe_limit,
            )
        return tuple(_task_from_row(row) for row in rows)

    async def snapshot(self) -> AITaskQueueSnapshot:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT
                       COUNT(*) FILTER (WHERE status='queued') AS queued,
                       COUNT(*) FILTER (WHERE status='running') AS running,
                       COUNT(*) FILTER (WHERE status='success') AS success,
                       COUNT(*) FILTER (WHERE status='error') AS error,
                       COUNT(*) FILTER (WHERE status='cancelled') AS cancelled
                   FROM ai_tasks"""
            )
            runtime = await connection.fetchrow(
                """SELECT paused,pause_reason
                   FROM ai_runtime_state WHERE singleton_id=1"""
            )
        return AITaskQueueSnapshot(
            queued=int(row["queued"] or 0) if row is not None else 0,
            running=int(row["running"] or 0) if row is not None else 0,
            success=int(row["success"] or 0) if row is not None else 0,
            error=int(row["error"] or 0) if row is not None else 0,
            cancelled=int(row["cancelled"] or 0) if row is not None else 0,
            paused=bool(runtime["paused"]) if runtime is not None else False,
            pause_reason=(
                str(runtime["pause_reason"] or "") or None
                if runtime is not None
                else None
            ),
        )

    async def recent(self, *, limit: int = 20) -> tuple[AITask, ...]:
        safe_limit = max(1, min(int(limit), 200))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                f"""SELECT {_columns()}
                   FROM ai_tasks
                   ORDER BY updated_at DESC,id DESC
                   LIMIT $1::INTEGER""",
                safe_limit,
            )
        return tuple(_task_from_row(row) for row in rows)

    async def get(self, *, task_id: UUID) -> AITask | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                f"SELECT {_columns()} FROM ai_tasks WHERE id=$1::UUID",
                task_id,
            )
        return _task_from_row(row) if row is not None else None

    async def _enqueue_on_connection(
        self,
        connection: Any,
        request: AITaskRequest,
    ) -> AITaskEnqueueResult:
        task_id = uuid4()
        not_before = request.not_before or datetime.now(timezone.utc)
        dedupe_key = request.dedupe_key.strip() if request.dedupe_key else None
        row = await connection.fetchrow(
            f"""INSERT INTO ai_tasks(
                   id,scope,task_type,status,priority,payload,dedupe_key,max_attempts,
                   not_before,created_by,estimated_cost_rub)
               VALUES(
                   $1::UUID,$2::VARCHAR,$3::VARCHAR,'queued',$4::SMALLINT,$5::JSONB,
                   $6::VARCHAR,$7::INTEGER,$8::TIMESTAMPTZ,$9::BIGINT,$10::NUMERIC)
               ON CONFLICT (dedupe_key)
               WHERE dedupe_key IS NOT NULL AND status IN ('queued','running')
               DO NOTHING
               RETURNING {_columns()}""",
            task_id,
            request.scope.value,
            request.task_type.strip(),
            int(request.priority),
            json.dumps(dict(request.payload), ensure_ascii=False, default=str),
            dedupe_key,
            int(request.max_attempts),
            not_before,
            request.created_by,
            request.estimated_cost_rub,
        )
        if row is not None:
            return AITaskEnqueueResult(task=_task_from_row(row), created=True)
        if dedupe_key is None:
            raise RuntimeError("Не удалось поставить AI-задачу в очередь.")
        existing = await connection.fetchrow(
            f"""SELECT {_columns()}
               FROM ai_tasks
               WHERE dedupe_key=$1::VARCHAR AND status IN ('queued','running')
               ORDER BY created_at ASC
               LIMIT 1""",
            dedupe_key,
        )
        if existing is None:
            raise RuntimeError("Активная dedupe AI-задача не найдена после конфликта.")
        return AITaskEnqueueResult(task=_task_from_row(existing), created=False)


def _worker_id(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("AI worker_id не может быть пустым.")
    return normalized[:120]


def _json_mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, Mapping):
            return dict(decoded)
    return {}


def _task_from_row(row: Mapping[str, Any]) -> AITask:
    return AITask(
        id=row["id"],
        scope=AIBudgetScope(str(row["scope"])),
        task_type=str(row["task_type"]),
        status=AITaskStatus(str(row["status"])),
        priority=int(row["priority"]),
        payload=_json_mapping(row["payload"]),
        result=_json_mapping(row["result"]),
        dedupe_key=str(row["dedupe_key"] or "") or None,
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
        not_before=row["not_before"],
        locked_by=str(row["locked_by"] or "") or None,
        locked_at=row["locked_at"],
        last_error_type=str(row["last_error_type"] or "") or None,
        last_error=str(row["last_error"] or "") or None,
        last_retry_delay_seconds=(
            int(row["last_retry_delay_seconds"])
            if row["last_retry_delay_seconds"] is not None
            else None
        ),
        estimated_cost_rub=Decimal(row["estimated_cost_rub"] or 0),
        created_by=int(row["created_by"]) if row["created_by"] is not None else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
    )


__all__ = ("AITaskRepository",)
