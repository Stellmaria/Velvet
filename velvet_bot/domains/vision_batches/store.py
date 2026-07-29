from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from velvet_bot.ai_vision import VisionAnalysisTarget
from velvet_bot.database import Database
from velvet_bot.domains.vision_batches.models import (
    VisionBatchPlan,
    VisionBatchProgress,
    VisionBatchStatus,
)


_BATCH_COLUMNS = """
    id,task_type,status,candidate_ids,candidate_count,created_task_count,
    deduplicated_task_count,max_cost_per_item_rub,estimated_cost_rub,
    prompt_version,created_by,expires_at,started_at,completed_at,last_error,
    metadata,created_at,updated_at
"""


class VisionBatchRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def find_candidates(self, *, limit: int) -> tuple[int, ...]:
        safe_limit = max(1, min(int(limit), 5000))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT mf.id
                FROM media_files AS mf
                LEFT JOIN media_ai_profiles AS profile ON profile.media_id=mf.id
                WHERE (
                        mf.media_type='photo'
                        OR (
                            mf.media_type='document'
                            AND COALESCE(mf.mime_type,'') LIKE 'image/%'
                        )
                      )
                  AND mf.media_set_id IS NULL
                  AND (
                        profile.media_id IS NULL
                        OR profile.status IN ('pending','error')
                      )
                  AND NOT EXISTS (
                        SELECT 1
                        FROM ai_tasks AS task
                        WHERE task.task_type='vision.semantic-profile'
                          AND task.status IN ('queued','running')
                          AND NULLIF(task.payload->>'media_id','')::BIGINT=mf.id
                      )
                ORDER BY COALESCE(profile.updated_at,mf.created_at),mf.id
                LIMIT $1::INTEGER
                """,
                safe_limit,
            )
        return tuple(int(row["id"]) for row in rows)

    async def create_plan(
        self,
        *,
        plan_id: UUID,
        candidate_ids: Sequence[int],
        max_cost_per_item_rub: Decimal,
        estimated_cost_rub: Decimal,
        prompt_version: int,
        created_by: int | None,
        expires_at: datetime,
        metadata: Mapping[str, object],
    ) -> VisionBatchPlan:
        normalized_ids = tuple(dict.fromkeys(int(value) for value in candidate_ids))
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                INSERT INTO ai_task_batches(
                    id,task_type,status,candidate_ids,candidate_count,
                    max_cost_per_item_rub,estimated_cost_rub,prompt_version,
                    created_by,expires_at,metadata
                )
                VALUES(
                    $1::UUID,'vision.semantic-profile','planned',$2::JSONB,$3::INTEGER,
                    $4::NUMERIC,$5::NUMERIC,$6::INTEGER,$7::BIGINT,$8::TIMESTAMPTZ,
                    $9::JSONB
                )
                RETURNING {_BATCH_COLUMNS}
                """,
                plan_id,
                json.dumps(normalized_ids),
                len(normalized_ids),
                max_cost_per_item_rub,
                estimated_cost_rub,
                max(1, int(prompt_version)),
                created_by,
                expires_at,
                json.dumps(dict(metadata), ensure_ascii=False, default=str),
            )
        if row is None:
            raise RuntimeError("PostgreSQL не вернул созданный план VL-партии.")
        return _plan_from_row(row)

    async def get(self, *, plan_id: UUID) -> VisionBatchPlan | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                f"SELECT {_BATCH_COLUMNS} FROM ai_task_batches WHERE id=$1::UUID",
                plan_id,
            )
        return _plan_from_row(row) if row is not None else None

    async def latest(self, *, created_by: int | None = None) -> VisionBatchPlan | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                SELECT {_BATCH_COLUMNS}
                FROM ai_task_batches
                WHERE ($1::BIGINT IS NULL OR created_by=$1::BIGINT)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                created_by,
            )
        return _plan_from_row(row) if row is not None else None

    async def claim_start(self, *, plan_id: UUID) -> VisionBatchPlan | None:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE ai_task_batches
                    SET status='expired',completed_at=NOW(),updated_at=NOW()
                    WHERE id=$1::UUID AND status='planned' AND expires_at<=NOW()
                    """,
                    plan_id,
                )
                await connection.execute(
                    """
                    UPDATE ai_task_batches
                    SET status='planned',last_error='Recovered stale batch start.',
                        updated_at=NOW()
                    WHERE id=$1::UUID AND status='starting'
                      AND started_at<NOW()-INTERVAL '5 minutes'
                      AND expires_at>NOW()
                    """,
                    plan_id,
                )
                row = await connection.fetchrow(
                    f"""
                    UPDATE ai_task_batches
                    SET status='starting',started_at=NOW(),last_error=NULL,updated_at=NOW()
                    WHERE id=$1::UUID AND status='planned' AND expires_at>NOW()
                    RETURNING {_BATCH_COLUMNS}
                    """,
                    plan_id,
                )
        return _plan_from_row(row) if row is not None else None

    async def attach_created_tasks(
        self,
        *,
        plan_id: UUID,
        task_ids: Sequence[UUID],
    ) -> int:
        if not task_ids:
            return 0
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE ai_tasks
                SET batch_id=$1::UUID,updated_at=NOW()
                WHERE id=ANY($2::UUID[])
                  AND (batch_id IS NULL OR batch_id=$1::UUID)
                """,
                plan_id,
                list(task_ids),
            )
        return int(result.rsplit(" ", 1)[-1])

    async def mark_queued(
        self,
        *,
        plan_id: UUID,
        created_task_count: int,
        deduplicated_task_count: int,
    ) -> VisionBatchPlan:
        del created_task_count, deduplicated_task_count
        async with self._database.acquire() as connection:
            async with connection.transaction():
                plan_row = await connection.fetchrow(
                    """
                    SELECT candidate_count
                    FROM ai_task_batches
                    WHERE id=$1::UUID AND status='starting'
                    FOR UPDATE
                    """,
                    plan_id,
                )
                if plan_row is None:
                    raise RuntimeError("Не удалось завершить постановку VL-партии.")
                linked = int(
                    await connection.fetchval(
                        "SELECT COUNT(*) FROM ai_tasks WHERE batch_id=$1::UUID",
                        plan_id,
                    )
                    or 0
                )
                candidate_count = int(plan_row["candidate_count"] or 0)
                created = min(candidate_count, linked)
                deduplicated = max(0, candidate_count - created)
                status = "queued" if created > 0 else "completed"
                row = await connection.fetchrow(
                    f"""
                    UPDATE ai_task_batches
                    SET status=$4::VARCHAR,created_task_count=$2::INTEGER,
                        deduplicated_task_count=$3::INTEGER,
                        completed_at=CASE WHEN $4::VARCHAR='completed' THEN NOW() ELSE NULL END,
                        updated_at=NOW()
                    WHERE id=$1::UUID AND status='starting'
                    RETURNING {_BATCH_COLUMNS}
                    """,
                    plan_id,
                    created,
                    deduplicated,
                    status,
                )
        if row is None:
            raise RuntimeError("Не удалось завершить постановку VL-партии.")
        return _plan_from_row(row)

    async def mark_error(self, *, plan_id: UUID, error: BaseException) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE ai_task_batches
                SET status='error',last_error=$2::TEXT,completed_at=NOW(),updated_at=NOW()
                WHERE id=$1::UUID AND status IN ('planned','starting','queued')
                """,
                plan_id,
                str(error)[:8000],
            )

    async def cancel(self, *, plan_id: UUID, reason: str) -> VisionBatchPlan | None:
        cancellation_reason = reason.strip()[:8000] or "VL-партия отменена владельцем."
        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    f"""
                    UPDATE ai_task_batches
                    SET status='cancelled',last_error=$2::TEXT,completed_at=NOW(),
                        updated_at=NOW()
                    WHERE id=$1::UUID
                      AND status IN ('planned','starting','queued','error')
                    RETURNING {_BATCH_COLUMNS}
                    """,
                    plan_id,
                    cancellation_reason,
                )
                if row is None:
                    return None
                await connection.execute(
                    """
                    UPDATE ai_tasks
                    SET status='cancelled',locked_by=NULL,locked_at=NULL,
                        last_error_type='BatchCancelled',last_error=$2::TEXT,
                        completed_at=NOW(),updated_at=NOW()
                    WHERE batch_id=$1::UUID AND status='queued'
                    """,
                    plan_id,
                    cancellation_reason,
                )
        return _plan_from_row(row)

    async def progress(self, *, plan_id: UUID) -> VisionBatchProgress | None:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                plan_row = await connection.fetchrow(
                    f"SELECT {_BATCH_COLUMNS} FROM ai_task_batches WHERE id=$1::UUID FOR UPDATE",
                    plan_id,
                )
                if plan_row is None:
                    return None
                counts = await connection.fetchrow(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE status='queued') AS queued,
                        COUNT(*) FILTER (WHERE status='running') AS running,
                        COUNT(*) FILTER (WHERE status='success') AS success,
                        COUNT(*) FILTER (WHERE status='error') AS error,
                        COUNT(*) FILTER (WHERE status='cancelled') AS cancelled
                    FROM ai_tasks
                    WHERE batch_id=$1::UUID
                    """,
                    plan_id,
                )
                queued = int(counts["queued"] or 0)
                running = int(counts["running"] or 0)
                success = int(counts["success"] or 0)
                error = int(counts["error"] or 0)
                cancelled = int(counts["cancelled"] or 0)
                total = queued + running + success + error + cancelled
                plan = _plan_from_row(plan_row)
                if plan.status is VisionBatchStatus.STARTING and total > 0:
                    recovered_row = await connection.fetchrow(
                        f"""
                        UPDATE ai_task_batches
                        SET status='queued',created_task_count=LEAST(candidate_count,$2::INTEGER),
                            deduplicated_task_count=GREATEST(0,candidate_count-$2::INTEGER),
                            last_error='Recovered batch progress after interrupted start.',
                            updated_at=NOW()
                        WHERE id=$1::UUID AND status='starting'
                        RETURNING {_BATCH_COLUMNS}
                        """,
                        plan_id,
                        total,
                    )
                    if recovered_row is not None:
                        plan = _plan_from_row(recovered_row)
                if (
                    plan.status is VisionBatchStatus.QUEUED
                    and total > 0
                    and queued == 0
                    and running == 0
                ):
                    completed_row = await connection.fetchrow(
                        f"""
                        UPDATE ai_task_batches
                        SET status='completed',completed_at=NOW(),updated_at=NOW()
                        WHERE id=$1::UUID AND status='queued'
                        RETURNING {_BATCH_COLUMNS}
                        """,
                        plan_id,
                    )
                    if completed_row is not None:
                        plan = _plan_from_row(completed_row)
        return VisionBatchProgress(
            plan=plan,
            queued=queued,
            running=running,
            success=success,
            error=error,
            cancelled=cancelled,
        )

    async def claim_media_target(
        self,
        *,
        media_id: int,
        provider: str,
        model: str,
        max_attempts: int,
    ) -> VisionAnalysisTarget | None:
        safe_attempts = max(1, min(int(max_attempts), 10))
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO media_ai_profiles(media_id,status)
                    SELECT id,'pending' FROM media_files WHERE id=$1::BIGINT
                    ON CONFLICT (media_id) DO NOTHING
                    """,
                    int(media_id),
                )
                row = await connection.fetchrow(
                    """
                    SELECT profile.status,profile.attempt_count,
                           media.telegram_file_id,media.preview_file_id,media.mime_type
                    FROM media_ai_profiles AS profile
                    JOIN media_files AS media ON media.id=profile.media_id
                    WHERE profile.media_id=$1::BIGINT
                    FOR UPDATE OF profile
                    """,
                    int(media_id),
                )
                if row is None or str(row["status"]) == "ready":
                    return None
                if str(row["status"]) == "processing":
                    return None
                if int(row["attempt_count"] or 0) >= safe_attempts:
                    return None
                await connection.execute(
                    """
                    UPDATE media_ai_profiles
                    SET status='processing',provider=$2::VARCHAR,model=$3::VARCHAR,
                        attempt_count=attempt_count+1,error_message=NULL,updated_at=NOW()
                    WHERE media_id=$1::BIGINT
                    """,
                    int(media_id),
                    provider,
                    model[:160],
                )
        return VisionAnalysisTarget(
            media_id=int(media_id),
            telegram_file_id=str(row["telegram_file_id"]),
            preview_file_id=(
                str(row["preview_file_id"])
                if row["preview_file_id"] is not None
                else None
            ),
            mime_type=row["mime_type"],
        )


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


def _candidate_ids(value: object) -> tuple[int, ...]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    result: list[int] = []
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return tuple(result)


def _plan_from_row(row: Mapping[str, Any]) -> VisionBatchPlan:
    return VisionBatchPlan(
        id=row["id"],
        task_type=str(row["task_type"]),
        status=VisionBatchStatus(str(row["status"])),
        candidate_ids=_candidate_ids(row["candidate_ids"]),
        candidate_count=int(row["candidate_count"] or 0),
        created_task_count=int(row["created_task_count"] or 0),
        deduplicated_task_count=int(row["deduplicated_task_count"] or 0),
        max_cost_per_item_rub=Decimal(row["max_cost_per_item_rub"] or 0),
        estimated_cost_rub=Decimal(row["estimated_cost_rub"] or 0),
        prompt_version=int(row["prompt_version"] or 1),
        created_by=int(row["created_by"]) if row["created_by"] is not None else None,
        expires_at=row["expires_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        last_error=str(row["last_error"] or "") or None,
        metadata=_json_mapping(row["metadata"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


__all__ = ("VisionBatchRepository",)
