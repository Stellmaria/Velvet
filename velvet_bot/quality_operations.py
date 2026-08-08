from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from velvet_bot.database import Database


_PLAN_KINDS = {"recent", "errors"}


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

    @staticmethod
    def _plan_from_row(row: Any) -> QualityQueuePlan:
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
            async with connection.transaction():
                await connection.execute(
                    """
                    DELETE FROM media_ai_quality_queue_plans
                    WHERE started_at IS NULL
                      AND expires_at < NOW() - INTERVAL '1 day'
                    """
                )
                if kind == "recent":
                    candidates = await connection.fetch(
                        """
                        SELECT
                            mf.id AS media_id,
                            CASE
                                WHEN q.media_id IS NULL THEN 'new'
                                WHEN q.status = 'pending' THEN 'legacy_pending'
                                ELSE 'failed'
                            END AS candidate_kind
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
                        ORDER BY mf.id DESC
                        LIMIT $1::INTEGER
                        """,
                        safe_limit,
                    )
                else:
                    candidates = await connection.fetch(
                        """
                        SELECT q.media_id, 'failed' AS candidate_kind
                        FROM media_ai_quality_checks AS q
                        JOIN media_files AS mf ON mf.id = q.media_id
                        WHERE q.decision IS NULL
                          AND q.status IN ('error', 'skipped')
                          AND (
                                mf.media_type = 'photo'
                                OR (
                                    mf.media_type = 'document'
                                    AND COALESCE(mf.mime_type, '') LIKE 'image/%'
                                )
                              )
                        ORDER BY q.updated_at DESC, q.media_id DESC
                        LIMIT $1::INTEGER
                        """,
                        safe_limit,
                    )

                media_ids = [int(row["media_id"]) for row in candidates]
                new_count = sum(
                    1 for row in candidates if row["candidate_kind"] == "new"
                )
                legacy_pending_count = sum(
                    1
                    for row in candidates
                    if row["candidate_kind"] == "legacy_pending"
                )
                failed_count = sum(
                    1 for row in candidates if row["candidate_kind"] == "failed"
                )
                row = await connection.fetchrow(
                    """
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
                    VALUES (
                        $1::BIGINT,
                        $2::VARCHAR,
                        $3::SMALLINT,
                        $4::BIGINT[],
                        $5::SMALLINT,
                        $6::SMALLINT,
                        $7::SMALLINT,
                        NOW() + INTERVAL '15 minutes'
                    )
                    RETURNING *
                    """,
                    int(requested_by),
                    kind,
                    safe_limit,
                    media_ids,
                    new_count,
                    legacy_pending_count,
                    failed_count,
                )
        return self._plan_from_row(row)

    async def get_plan(
        self,
        plan_id: int,
        *,
        requested_by: int,
    ) -> QualityQueuePlan | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT *
                FROM media_ai_quality_queue_plans
                WHERE id = $1::BIGINT
                  AND requested_by = $2::BIGINT
                """,
                int(plan_id),
                int(requested_by),
            )
        return self._plan_from_row(row) if row is not None else None

    async def start_plan(
        self,
        plan_id: int,
        *,
        requested_by: int,
    ) -> int:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                plan = await connection.fetchrow(
                    """
                    SELECT *
                    FROM media_ai_quality_queue_plans
                    WHERE id = $1::BIGINT
                      AND requested_by = $2::BIGINT
                    FOR UPDATE
                    """,
                    int(plan_id),
                    int(requested_by),
                )
                if plan is None:
                    raise ValueError("План quality queue не найден.")
                if plan["started_at"] is not None:
                    raise ValueError("Этот план уже был запущен.")
                if plan["expires_at"] <= datetime.now(tz=plan["expires_at"].tzinfo):
                    raise ValueError("План устарел. Сформируйте новый.")

                media_ids = [int(value) for value in (plan["media_ids"] or ())]
                if media_ids:
                    rows = await connection.fetch(
                        """
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
                            $2::BIGINT,
                            NOW()
                        FROM unnest($1::BIGINT[]) AS source(media_id)
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
                        """,
                        media_ids,
                        int(plan_id),
                    )
                else:
                    rows = []
                started_count = len(rows)
                await connection.execute(
                    """
                    UPDATE media_ai_quality_queue_plans
                    SET started_at = NOW(),
                        started_count = $2::SMALLINT
                    WHERE id = $1::BIGINT
                    """,
                    int(plan_id),
                    started_count,
                )
        return started_count


__all__ = ("QualityOperationsRepository", "QualityQueuePlan")
