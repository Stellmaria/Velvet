from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from velvet_bot.database import Database


_PLAN_KINDS = {"recent", "errors"}

_CREATE_PLAN_SQL = """
    WITH candidates AS (
        SELECT
            mf.id AS media_id,
            CASE
                WHEN q.media_id IS NULL THEN 'new'
                WHEN q.status = 'pending' THEN 'legacy_pending'
                ELSE 'failed'
            END AS candidate_kind,
            q.updated_at AS quality_updated_at
        FROM media_files AS mf
        LEFT JOIN media_ai_quality_checks AS q
               ON q.media_id = mf.id
        WHERE (
                mf.media_type = 'photo'
                OR (
                    mf.media_type = 'document'
                    AND COALESCE(mf.mime_type, '') LIKE 'image/%'
                )
              )
          AND (
                (
                    $2::VARCHAR = 'recent'
                    AND (
                        q.media_id IS NULL
                        OR (
                            q.decision IS NULL
                            AND q.status IN ('pending', 'error', 'skipped')
                            AND (
                                q.status <> 'pending'
                                OR q.queue_plan_id IS NULL
                            )
                        )
                    )
                )
                OR (
                    $2::VARCHAR = 'errors'
                    AND q.decision IS NULL
                    AND q.status IN ('error', 'skipped')
                )
              )
        ORDER BY
            CASE WHEN $2::VARCHAR = 'recent' THEN mf.id END DESC,
            CASE WHEN $2::VARCHAR = 'errors' THEN q.updated_at END DESC NULLS LAST,
            mf.id DESC
        LIMIT $3::INTEGER
    ),
    stats AS (
        SELECT
            COALESCE(
                ARRAY_AGG(media_id ORDER BY media_id DESC),
                ARRAY[]::BIGINT[]
            ) AS media_ids,
            COUNT(*) FILTER (WHERE candidate_kind = 'new')::SMALLINT AS new_count,
            COUNT(*) FILTER (
                WHERE candidate_kind = 'legacy_pending'
            )::SMALLINT AS legacy_pending_count,
            COUNT(*) FILTER (WHERE candidate_kind = 'failed')::SMALLINT AS failed_count
        FROM candidates
    )
    INSERT INTO media_ai_quality_queue_plans (
        requested_by,
        kind,
        requested_limit,
        media_ids,
        new_count,
        legacy_pending_count,
        failed_count,
        expires_at
    )
    SELECT
        $1::BIGINT,
        $2::VARCHAR,
        $3::SMALLINT,
        stats.media_ids,
        stats.new_count,
        stats.legacy_pending_count,
        stats.failed_count,
        NOW() + INTERVAL '15 minutes'
    FROM stats
    RETURNING *
"""

_START_PLAN_SQL = """
    WITH selected_plan AS (
        SELECT id, media_ids
        FROM media_ai_quality_queue_plans
        WHERE id = $1::BIGINT
          AND requested_by = $2::BIGINT
          AND started_at IS NULL
          AND expires_at > NOW()
        FOR UPDATE
    ),
    queued AS (
        INSERT INTO media_ai_quality_checks AS quality (
            media_id,
            status,
            attempt_count,
            queue_plan_id,
            updated_at
        )
        SELECT
            source.media_id,
            'pending',
            0,
            selected_plan.id,
            NOW()
        FROM selected_plan
        CROSS JOIN LATERAL unnest(selected_plan.media_ids) AS source(media_id)
        JOIN media_files AS mf ON mf.id = source.media_id
        WHERE (
                mf.media_type = 'photo'
                OR (
                    mf.media_type = 'document'
                    AND COALESCE(mf.mime_type, '') LIKE 'image/%'
                )
              )
        ON CONFLICT (media_id) DO UPDATE
        SET status = 'pending',
            attempt_count = 0,
            provider = NULL,
            model = NULL,
            verdict = NULL,
            quality_score = NULL,
            confidence = NULL,
            report = NULL,
            decision = NULL,
            decided_by = NULL,
            decided_at = NULL,
            error_message = NULL,
            analyzed_at = NULL,
            queue_plan_id = EXCLUDED.queue_plan_id,
            updated_at = NOW()
        WHERE quality.decision IS NULL
          AND quality.status IN ('pending', 'error', 'skipped')
          AND (
                quality.status <> 'pending'
                OR quality.queue_plan_id IS NULL
              )
        RETURNING media_id
    ),
    completed AS (
        UPDATE media_ai_quality_queue_plans AS plan
        SET started_at = NOW(),
            started_count = (SELECT COUNT(*)::SMALLINT FROM queued)
        FROM selected_plan
        WHERE plan.id = selected_plan.id
        RETURNING plan.started_count
    )
    SELECT started_count FROM completed
"""


@dataclass(frozen=True, slots=True)
class QualityQueuePlan:
    plan_id: int
    requested_by: int
    kind: str
    requested_limit: int
    media_ids: tuple[int, ...]
    new_count: int
    legacy_pending_count: int
    failed_count: int
    created_at: datetime
    expires_at: datetime
    started_at: datetime | None
    started_count: int | None

    @property
    def selected_count(self) -> int:
        return len(self.media_ids)

    @property
    def started(self) -> bool:
        return self.started_at is not None


class QualityOperationsRepository:
    """Owner-controlled queue planning for global Qwen quality checks."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def _safe_limit(limit: int) -> int:
        return max(1, min(int(limit), 100))

    async def plan_recent(
        self,
        *,
        requested_by: int,
        limit: int,
    ) -> QualityQueuePlan:
        return await self._create_plan(
            requested_by=requested_by,
            kind="recent",
            limit=limit,
        )

    async def plan_errors(
        self,
        *,
        requested_by: int,
        limit: int = 10,
    ) -> QualityQueuePlan:
        return await self._create_plan(
            requested_by=requested_by,
            kind="errors",
            limit=limit,
        )

    async def _create_plan(
        self,
        *,
        requested_by: int,
        kind: str,
        limit: int,
    ) -> QualityQueuePlan:
        if kind not in _PLAN_KINDS:
            raise ValueError("Неизвестный тип плана quality queue.")
        safe_limit = self._safe_limit(limit)
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                _CREATE_PLAN_SQL,
                int(requested_by),
                kind,
                safe_limit,
            )
        if row is None:
            raise RuntimeError("Не удалось сохранить plan quality queue.")
        return QualityQueuePlan(
            plan_id=int(row["id"]),
            requested_by=int(row["requested_by"]),
            kind=str(row["kind"]),
            requested_limit=int(row["requested_limit"]),
            media_ids=tuple(int(value) for value in (row["media_ids"] or ())),
            new_count=int(row["new_count"] or 0),
            legacy_pending_count=int(row["legacy_pending_count"] or 0),
            failed_count=int(row["failed_count"] or 0),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            started_at=row["started_at"],
            started_count=(
                int(row["started_count"])
                if row["started_count"] is not None
                else None
            ),
        )

    async def start_plan(
        self,
        plan_id: int,
        *,
        requested_by: int,
    ) -> int:
        async with self._database.acquire() as connection:
            started_count = await connection.fetchval(
                _START_PLAN_SQL,
                int(plan_id),
                int(requested_by),
            )
        if started_count is None:
            raise ValueError(
                "План не найден, устарел или уже был запущен. Сформируйте новый."
            )
        return int(started_count)


__all__ = ("QualityOperationsRepository", "QualityQueuePlan")
