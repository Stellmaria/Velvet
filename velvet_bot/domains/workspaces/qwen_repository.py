from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from velvet_bot.database import Database
from velvet_bot.quality_calibration import (
    CalibrationProfile,
    FeedbackSample,
    build_calibration_profile,
)


@dataclass(frozen=True, slots=True)
class WorkspaceQwenTarget:
    workspace_id: int
    media_id: int
    telegram_file_id: str
    preview_file_id: str | None
    mime_type: str | None


@dataclass(frozen=True, slots=True)
class WorkspaceQwenCheck:
    workspace_id: int
    media_id: int
    file_name: str
    media_type: str
    telegram_file_id: str
    preview_file_id: str | None
    status: str
    verdict: str | None
    quality_score: int | None
    confidence: int | None
    report: dict[str, Any] | None
    decision: str | None
    error_message: str | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceQwenSummary:
    pending: int
    processing: int
    ready: int
    errors: int
    skipped: int
    unreviewed: int
    accepted: int
    fix_required: int
    clean: int
    warnings: int
    critical: int


@dataclass(frozen=True, slots=True)
class WorkspaceQwenPage:
    items: tuple[WorkspaceQwenCheck, ...]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


@dataclass(frozen=True, slots=True)
class WorkspaceQwenJob:
    id: int
    workspace_id: int
    kind: str
    status: str
    stage: str
    title: str
    provider: str | None
    model: str | None
    media_id: int | None
    request_payload: dict[str, Any]
    result_payload: dict[str, Any] | None
    result_text: str | None
    error_message: str | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceQwenJobPage:
    items: tuple[WorkspaceQwenJob, ...]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


def _decode_json(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None
    return None


class WorkspaceQwenRepository:
    """Workspace-isolated Qwen checks and user-visible AI job history."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def _check_from_row(row: Any) -> WorkspaceQwenCheck:
        return WorkspaceQwenCheck(
            workspace_id=int(row["workspace_id"]),
            media_id=int(row["media_id"]),
            file_name=str(row["file_name"] or f"media-{row['media_id']}"),
            media_type=str(row["media_type"]),
            telegram_file_id=str(row["telegram_file_id"]),
            preview_file_id=(
                str(row["preview_file_id"])
                if row["preview_file_id"] is not None
                else None
            ),
            status=str(row["status"]),
            verdict=str(row["verdict"]) if row["verdict"] is not None else None,
            quality_score=(
                int(row["quality_score"])
                if row["quality_score"] is not None
                else None
            ),
            confidence=(
                int(row["confidence"])
                if row["confidence"] is not None
                else None
            ),
            report=_decode_json(row["report"]),
            decision=str(row["decision"]) if row["decision"] is not None else None,
            error_message=(
                str(row["error_message"])
                if row["error_message"] is not None
                else None
            ),
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _job_from_row(row: Any) -> WorkspaceQwenJob:
        return WorkspaceQwenJob(
            id=int(row["id"]),
            workspace_id=int(row["workspace_id"]),
            kind=str(row["kind"]),
            status=str(row["status"]),
            stage=str(row["stage"]),
            title=str(row["title"]),
            provider=str(row["provider"]) if row["provider"] is not None else None,
            model=str(row["model"]) if row["model"] is not None else None,
            media_id=int(row["media_id"]) if row["media_id"] is not None else None,
            request_payload=_decode_json(row["request_payload"]) or {},
            result_payload=_decode_json(row["result_payload"]),
            result_text=(
                str(row["result_text"]) if row["result_text"] is not None else None
            ),
            error_message=(
                str(row["error_message"])
                if row["error_message"] is not None
                else None
            ),
            created_by=(
                int(row["created_by"]) if row["created_by"] is not None else None
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def media_belongs_to_workspace(self, workspace_id: int, media_id: int) -> bool:
        async with self._database.acquire() as connection:
            return bool(
                await connection.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM character_media AS link
                        JOIN characters AS character
                          ON character.id = link.character_id
                        JOIN media_files AS media
                          ON media.id = link.media_id
                        WHERE character.workspace_id = $1::BIGINT
                          AND link.media_id = $2::BIGINT
                          AND (
                                media.media_type = 'photo'
                                OR (
                                    media.media_type = 'document'
                                    AND COALESCE(media.mime_type, '') LIKE 'image/%'
                                )
                              )
                    )
                    """,
                    int(workspace_id),
                    int(media_id),
                )
            )

    async def enqueue_media(
        self,
        *,
        workspace_id: int,
        media_id: int,
        force: bool = False,
    ) -> bool:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                exists = await connection.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM character_media AS link
                        JOIN characters AS character
                          ON character.id = link.character_id
                        JOIN media_files AS media
                          ON media.id = link.media_id
                        WHERE character.workspace_id = $1::BIGINT
                          AND link.media_id = $2::BIGINT
                          AND (
                                media.media_type = 'photo'
                                OR (
                                    media.media_type = 'document'
                                    AND COALESCE(media.mime_type, '') LIKE 'image/%'
                                )
                              )
                    )
                    """,
                    int(workspace_id),
                    int(media_id),
                )
                if not exists:
                    raise ValueError(
                        "Изображение не найдено в выбранном личном пространстве."
                    )
                if force:
                    result = await connection.execute(
                        """
                        INSERT INTO workspace_qwen_checks AS q (
                            workspace_id, media_id, status, attempt_count, updated_at
                        )
                        VALUES ($1::BIGINT, $2::BIGINT, 'pending', 0, NOW())
                        ON CONFLICT (workspace_id, media_id) DO UPDATE
                        SET status = 'pending',
                            attempt_count = 0,
                            verdict = NULL,
                            quality_score = NULL,
                            confidence = NULL,
                            report = NULL,
                            decision = NULL,
                            decided_by = NULL,
                            decided_at = NULL,
                            error_message = NULL,
                            analyzed_at = NULL,
                            updated_at = NOW()
                        """,
                        int(workspace_id),
                        int(media_id),
                    )
                    return result.endswith("1")
                result = await connection.execute(
                    """
                    INSERT INTO workspace_qwen_checks AS q (
                        workspace_id, media_id, status, attempt_count, updated_at
                    )
                    VALUES ($1::BIGINT, $2::BIGINT, 'pending', 0, NOW())
                    ON CONFLICT (workspace_id, media_id) DO UPDATE
                    SET status = 'pending',
                        attempt_count = 0,
                        error_message = NULL,
                        updated_at = NOW()
                    WHERE q.status IN ('error', 'skipped')
                    """,
                    int(workspace_id),
                    int(media_id),
                )
        return result.endswith("1")

    async def enqueue_archive(self, *, workspace_id: int, limit: int = 500) -> int:
        safe_limit = max(1, min(int(limit), 2000))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                WITH candidates AS (
                    SELECT DISTINCT media.id
                    FROM media_files AS media
                    JOIN character_media AS link ON link.media_id = media.id
                    JOIN characters AS character ON character.id = link.character_id
                    WHERE character.workspace_id = $1::BIGINT
                      AND (
                            media.media_type = 'photo'
                            OR (
                                media.media_type = 'document'
                                AND COALESCE(media.mime_type, '') LIKE 'image/%'
                            )
                          )
                    ORDER BY media.id DESC
                    LIMIT $2::INTEGER
                )
                INSERT INTO workspace_qwen_checks (
                    workspace_id, media_id, status, attempt_count, updated_at
                )
                SELECT $1::BIGINT, id, 'pending', 0, NOW()
                FROM candidates
                ON CONFLICT (workspace_id, media_id) DO NOTHING
                RETURNING media_id
                """,
                int(workspace_id),
                safe_limit,
            )
        return len(rows)

    async def claim_next(
        self,
        *,
        provider: str,
        model: str,
        max_attempts: int,
    ) -> WorkspaceQwenTarget | None:
        safe_attempts = max(1, min(int(max_attempts), 10))
        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    WITH candidate AS (
                        SELECT
                            q.workspace_id,
                            q.media_id,
                            media.telegram_file_id,
                            media.preview_file_id,
                            media.mime_type
                        FROM workspace_qwen_checks AS q
                        JOIN media_files AS media ON media.id = q.media_id
                        JOIN workspace_modules AS module
                          ON module.workspace_id = q.workspace_id
                         AND module.module_key = 'qwen'
                        JOIN workspace_settings AS settings
                          ON settings.workspace_id = q.workspace_id
                        WHERE module.is_allowed
                          AND module.is_enabled
                          AND settings.qwen_enabled
                          AND q.attempt_count < $1::SMALLINT
                          AND (
                                q.status = 'pending'
                                OR q.status = 'error'
                                OR (
                                    q.status = 'processing'
                                    AND q.updated_at < NOW() - INTERVAL '15 minutes'
                                )
                              )
                        ORDER BY q.updated_at, q.workspace_id, q.media_id
                        FOR UPDATE OF q SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE workspace_qwen_checks AS q
                    SET status = 'processing',
                        provider = $2::VARCHAR,
                        model = $3::VARCHAR,
                        attempt_count = q.attempt_count + 1,
                        error_message = NULL,
                        updated_at = NOW()
                    FROM candidate
                    WHERE q.workspace_id = candidate.workspace_id
                      AND q.media_id = candidate.media_id
                    RETURNING
                        candidate.workspace_id,
                        candidate.media_id,
                        candidate.telegram_file_id,
                        candidate.preview_file_id,
                        candidate.mime_type
                    """,
                    safe_attempts,
                    provider[:64],
                    model[:160],
                )
        if row is None:
            return None
        return WorkspaceQwenTarget(
            workspace_id=int(row["workspace_id"]),
            media_id=int(row["media_id"]),
            telegram_file_id=str(row["telegram_file_id"]),
            preview_file_id=(
                str(row["preview_file_id"])
                if row["preview_file_id"] is not None
                else None
            ),
            mime_type=str(row["mime_type"]) if row["mime_type"] is not None else None,
        )

    async def mark_ready(
        self,
        *,
        workspace_id: int,
        media_id: int,
        report: dict[str, Any],
    ) -> None:
        encoded = json.dumps(report, ensure_ascii=False)
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE workspace_qwen_checks
                    SET status = 'ready',
                        verdict = $3::VARCHAR,
                        quality_score = $4::SMALLINT,
                        confidence = $5::SMALLINT,
                        report = $6::JSONB,
                        error_message = NULL,
                        analyzed_at = NOW(),
                        updated_at = NOW()
                    WHERE workspace_id = $1::BIGINT
                      AND media_id = $2::BIGINT
                    """,
                    int(workspace_id),
                    int(media_id),
                    str(report["verdict"]),
                    int(report["quality_score"]),
                    int(report["confidence"]),
                    encoded,
                )
                changed = await connection.fetchval(
                    """
                    UPDATE media_rework_items
                    SET status = 'ready_for_review',
                        reason = COALESCE($3::JSONB ->> 'summary_ru', reason),
                        qwen_verdict = $3::JSONB ->> 'verdict',
                        qwen_score = ($3::JSONB ->> 'quality_score')::SMALLINT,
                        updated_at = NOW()
                    WHERE workspace_id = $1::BIGINT
                      AND media_id = $2::BIGINT
                      AND status = 'checking'
                    RETURNING media_id
                    """,
                    int(workspace_id),
                    int(media_id),
                    encoded,
                )
                if changed is not None:
                    await connection.execute(
                        """
                        INSERT INTO media_rework_events (
                            workspace_id, media_id, action, source, reason, payload
                        )
                        VALUES (
                            $1::BIGINT, $2::BIGINT, 'recheck_ready', 'system',
                            COALESCE($3::JSONB ->> 'summary_ru',
                                     'Повторная проверка Qwen завершена.'),
                            $3::JSONB
                        )
                        """,
                        int(workspace_id),
                        int(media_id),
                        encoded,
                    )

    async def mark_error(
        self,
        *,
        workspace_id: int,
        media_id: int,
        error: BaseException,
        max_attempts: int,
        permanent: bool = False,
    ) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE workspace_qwen_checks
                SET status = CASE
                        WHEN $4::BOOLEAN OR attempt_count >= $5::SMALLINT
                            THEN 'skipped'
                        ELSE 'error'
                    END,
                    error_message = $3::TEXT,
                    updated_at = NOW()
                WHERE workspace_id = $1::BIGINT
                  AND media_id = $2::BIGINT
                """,
                int(workspace_id),
                int(media_id),
                str(error)[:2000],
                bool(permanent),
                max(1, min(int(max_attempts), 10)),
            )

    async def summary(self, workspace_id: int) -> WorkspaceQwenSummary:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE status = 'processing') AS processing,
                    COUNT(*) FILTER (WHERE status = 'ready') AS ready,
                    COUNT(*) FILTER (WHERE status = 'error') AS errors,
                    COUNT(*) FILTER (WHERE status = 'skipped') AS skipped,
                    COUNT(*) FILTER (
                        WHERE status = 'ready' AND decision IS NULL
                    ) AS unreviewed,
                    COUNT(*) FILTER (WHERE decision = 'accepted') AS accepted,
                    COUNT(*) FILTER (WHERE decision = 'fix_required') AS fix_required,
                    COUNT(*) FILTER (
                        WHERE status = 'ready' AND verdict = 'ready'
                    ) AS clean,
                    COUNT(*) FILTER (
                        WHERE status = 'ready' AND verdict = 'review'
                    ) AS warnings,
                    COUNT(*) FILTER (
                        WHERE status = 'ready' AND verdict = 'critical'
                    ) AS critical
                FROM workspace_qwen_checks
                WHERE workspace_id = $1::BIGINT
                """,
                int(workspace_id),
            )
        return WorkspaceQwenSummary(
            **{key: int(row[key] or 0) for key in row.keys()}
        )

    @staticmethod
    def _section_condition(section: str) -> str:
        conditions = {
            "review": "q.status = 'ready' AND q.decision IS NULL",
            "accepted": "q.decision = 'accepted'",
            "fix": "q.decision = 'fix_required'",
            "errors": "q.status IN ('error', 'skipped')",
            "queue": "q.status IN ('pending', 'processing')",
        }
        if section not in conditions:
            raise ValueError("Неизвестный раздел Qwen-проверок.")
        return conditions[section]

    async def list_checks(
        self,
        *,
        workspace_id: int,
        section: str = "review",
        page: int = 0,
        page_size: int = 6,
    ) -> WorkspaceQwenPage:
        condition = self._section_condition(section)
        safe_size = max(1, min(int(page_size), 10))
        async with self._database.acquire() as connection:
            total = int(
                await connection.fetchval(
                    f"""
                    SELECT COUNT(*)
                    FROM workspace_qwen_checks AS q
                    WHERE q.workspace_id = $1::BIGINT AND {condition}
                    """,
                    int(workspace_id),
                )
                or 0
            )
            pages = max(1, (total + safe_size - 1) // safe_size)
            safe_page = min(max(0, int(page)), pages - 1)
            rows = await connection.fetch(
                f"""
                SELECT
                    q.*,
                    COALESCE(media.original_file_name, media.storage_file_name) AS file_name,
                    media.media_type,
                    media.telegram_file_id,
                    media.preview_file_id
                FROM workspace_qwen_checks AS q
                JOIN media_files AS media ON media.id = q.media_id
                WHERE q.workspace_id = $1::BIGINT AND {condition}
                ORDER BY
                    CASE q.verdict
                        WHEN 'critical' THEN 3
                        WHEN 'review' THEN 2
                        ELSE 1
                    END DESC,
                    q.updated_at DESC,
                    q.media_id DESC
                OFFSET $2::INTEGER LIMIT $3::INTEGER
                """,
                int(workspace_id),
                safe_page * safe_size,
                safe_size,
            )
        return WorkspaceQwenPage(
            items=tuple(self._check_from_row(row) for row in rows),
            page=safe_page,
            page_size=safe_size,
            total_items=total,
        )

    async def get_check(
        self,
        *,
        workspace_id: int,
        media_id: int,
    ) -> WorkspaceQwenCheck | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    q.*,
                    COALESCE(media.original_file_name, media.storage_file_name) AS file_name,
                    media.media_type,
                    media.telegram_file_id,
                    media.preview_file_id
                FROM workspace_qwen_checks AS q
                JOIN media_files AS media ON media.id = q.media_id
                WHERE q.workspace_id = $1::BIGINT
                  AND q.media_id = $2::BIGINT
                """,
                int(workspace_id),
                int(media_id),
            )
        return self._check_from_row(row) if row is not None else None

    async def set_decision(
        self,
        *,
        workspace_id: int,
        media_id: int,
        decision: str,
        user_id: int,
    ) -> bool:
        if decision not in {"accepted", "fix_required"}:
            raise ValueError("Неизвестное решение Qwen-проверки.")
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE workspace_qwen_checks
                SET decision = $3::VARCHAR,
                    decided_by = $4::BIGINT,
                    decided_at = NOW(),
                    updated_at = NOW()
                WHERE workspace_id = $1::BIGINT
                  AND media_id = $2::BIGINT
                  AND status = 'ready'
                """,
                int(workspace_id),
                int(media_id),
                decision,
                int(user_id),
            )
        return result.endswith("1")

    async def retry(self, *, workspace_id: int, media_id: int) -> bool:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE workspace_qwen_checks
                SET status = 'pending',
                    attempt_count = 0,
                    verdict = NULL,
                    quality_score = NULL,
                    confidence = NULL,
                    report = NULL,
                    decision = NULL,
                    decided_by = NULL,
                    decided_at = NULL,
                    error_message = NULL,
                    analyzed_at = NULL,
                    updated_at = NOW()
                WHERE workspace_id = $1::BIGINT
                  AND media_id = $2::BIGINT
                """,
                int(workspace_id),
                int(media_id),
            )
        return result.endswith("1")

    async def calibration_profile(
        self,
        *,
        workspace_id: int,
        provider: str,
        model: str,
        limit: int = 1000,
    ) -> CalibrationProfile:
        safe_limit = max(20, min(int(limit), 5000))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT predicted_verdict, quality_score, confidence,
                       owner_decision, outcome
                FROM workspace_qwen_feedback
                WHERE workspace_id = $1::BIGINT
                  AND provider = $2::VARCHAR
                  AND model = $3::VARCHAR
                ORDER BY created_at DESC, id DESC
                LIMIT $4::INTEGER
                """,
                int(workspace_id),
                provider,
                model,
                safe_limit,
            )
        return build_calibration_profile(
            FeedbackSample(
                predicted_verdict=str(row["predicted_verdict"]),
                quality_score=int(row["quality_score"]),
                confidence=int(row["confidence"]),
                owner_decision=str(row["owner_decision"]),
                outcome=str(row["outcome"]),
            )
            for row in rows
        )

    async def create_job(
        self,
        *,
        workspace_id: int,
        kind: str,
        title: str,
        provider: str | None,
        model: str | None,
        created_by: int | None,
        request_payload: dict[str, Any] | None = None,
        media_id: int | None = None,
    ) -> int:
        cleaned_title = " ".join(title.split()).strip()[:240]
        if not cleaned_title:
            raise ValueError("Название Qwen-задания не может быть пустым.")
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                INSERT INTO workspace_qwen_jobs (
                    workspace_id, kind, status, stage, title, provider, model,
                    media_id, request_payload, created_by
                )
                VALUES (
                    $1::BIGINT, $2::VARCHAR, 'pending', 'queued', $3::VARCHAR,
                    $4::VARCHAR, $5::VARCHAR, $6::BIGINT, $7::JSONB, $8::BIGINT
                )
                RETURNING id
                """,
                int(workspace_id),
                kind,
                cleaned_title,
                provider[:64] if provider else None,
                model[:160] if model else None,
                int(media_id) if media_id is not None else None,
                json.dumps(request_payload or {}, ensure_ascii=False),
                int(created_by) if created_by is not None else None,
            )
        return int(value)

    async def set_job_stage(self, job_id: int, stage: str) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE workspace_qwen_jobs
                SET status = 'processing',
                    stage = $2::VARCHAR,
                    started_at = COALESCE(started_at, NOW()),
                    updated_at = NOW(),
                    error_message = NULL
                WHERE id = $1::BIGINT
                """,
                int(job_id),
                stage[:32],
            )

    async def finish_job(
        self,
        *,
        job_id: int,
        result_text: str,
        result_payload: dict[str, Any],
    ) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE workspace_qwen_jobs
                SET status = 'ready',
                    stage = 'completed',
                    result_text = $2::TEXT,
                    result_payload = $3::JSONB,
                    error_message = NULL,
                    finished_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1::BIGINT
                """,
                int(job_id),
                result_text,
                json.dumps(result_payload, ensure_ascii=False),
            )

    async def fail_job(self, *, job_id: int, error: BaseException) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE workspace_qwen_jobs
                SET status = 'error',
                    stage = 'failed',
                    error_message = $2::TEXT,
                    finished_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1::BIGINT
                """,
                int(job_id),
                str(error)[:3000],
            )

    async def list_jobs(
        self,
        *,
        workspace_id: int,
        page: int = 0,
        page_size: int = 8,
    ) -> WorkspaceQwenJobPage:
        safe_size = max(1, min(int(page_size), 12))
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE workspace_qwen_jobs
                SET status = 'error',
                    stage = 'interrupted',
                    error_message = COALESCE(
                        error_message,
                        'Задание было прервано перезапуском бота.'
                    ),
                    finished_at = NOW(),
                    updated_at = NOW()
                WHERE workspace_id = $1::BIGINT
                  AND status = 'processing'
                  AND updated_at < NOW() - INTERVAL '30 minutes'
                """,
                int(workspace_id),
            )
            total = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM workspace_qwen_jobs
                    WHERE workspace_id = $1::BIGINT
                    """,
                    int(workspace_id),
                )
                or 0
            )
            pages = max(1, (total + safe_size - 1) // safe_size)
            safe_page = min(max(0, int(page)), pages - 1)
            rows = await connection.fetch(
                """
                SELECT *
                FROM workspace_qwen_jobs
                WHERE workspace_id = $1::BIGINT
                ORDER BY created_at DESC, id DESC
                OFFSET $2::INTEGER LIMIT $3::INTEGER
                """,
                int(workspace_id),
                safe_page * safe_size,
                safe_size,
            )
        return WorkspaceQwenJobPage(
            items=tuple(self._job_from_row(row) for row in rows),
            page=safe_page,
            page_size=safe_size,
            total_items=total,
        )

    async def get_job(
        self,
        *,
        workspace_id: int,
        job_id: int,
    ) -> WorkspaceQwenJob | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT *
                FROM workspace_qwen_jobs
                WHERE workspace_id = $1::BIGINT
                  AND id = $2::BIGINT
                """,
                int(workspace_id),
                int(job_id),
            )
        return self._job_from_row(row) if row is not None else None


__all__ = (
    "WorkspaceQwenCheck",
    "WorkspaceQwenJob",
    "WorkspaceQwenJobPage",
    "WorkspaceQwenPage",
    "WorkspaceQwenRepository",
    "WorkspaceQwenSummary",
    "WorkspaceQwenTarget",
)
