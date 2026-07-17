from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from velvet_bot.database import Database


AI_JOB_KINDS = frozenset(
    {
        "quality_image",
        "reference_comparison",
        "prompt_result",
        "palette_composition",
        "velvet_formatting",
        "media_set_consistency",
    }
)
AI_JOB_STATUSES = frozenset({"pending", "processing", "ready", "error"})


@dataclass(frozen=True, slots=True)
class AIJob:
    id: int
    kind: str
    status: str
    stage: str
    title: str
    provider: str | None
    model: str | None
    request_payload: dict[str, Any]
    result_payload: dict[str, Any] | None
    result_text: str | None
    result_reference_type: str | None
    result_reference_id: int | None
    error_message: str | None
    created_by: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AIJobPage:
    items: tuple[AIJob, ...]
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


class AIJobRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def _from_row(row: Any) -> AIJob:
        return AIJob(
            id=int(row["id"]),
            kind=str(row["kind"]),
            status=str(row["status"]),
            stage=str(row["stage"]),
            title=str(row["title"]),
            provider=str(row["provider"]) if row["provider"] is not None else None,
            model=str(row["model"]) if row["model"] is not None else None,
            request_payload=_decode_json(row["request_payload"]) or {},
            result_payload=_decode_json(row["result_payload"]),
            result_text=str(row["result_text"]) if row["result_text"] is not None else None,
            result_reference_type=(
                str(row["result_reference_type"])
                if row["result_reference_type"] is not None
                else None
            ),
            result_reference_id=(
                int(row["result_reference_id"])
                if row["result_reference_id"] is not None
                else None
            ),
            error_message=(
                str(row["error_message"]) if row["error_message"] is not None else None
            ),
            created_by=int(row["created_by"]) if row["created_by"] is not None else None,
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            updated_at=row["updated_at"],
        )

    async def create(
        self,
        *,
        kind: str,
        title: str,
        provider: str | None,
        model: str | None,
        request_payload: dict[str, Any] | None,
        created_by: int | None,
    ) -> int:
        cleaned_kind = kind.strip()
        if cleaned_kind not in AI_JOB_KINDS:
            raise ValueError("Неизвестный тип AI-задания.")
        cleaned_title = " ".join(title.split()).strip()[:240]
        if not cleaned_title:
            raise ValueError("Название AI-задания не может быть пустым.")
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                INSERT INTO ai_jobs (
                    kind, status, stage, title, provider, model,
                    request_payload, created_by
                )
                VALUES (
                    $1::VARCHAR, 'pending', 'queued', $2::VARCHAR,
                    $3::VARCHAR, $4::VARCHAR, $5::JSONB, $6::BIGINT
                )
                RETURNING id
                """,
                cleaned_kind,
                cleaned_title,
                provider[:64] if provider else None,
                model[:160] if model else None,
                json.dumps(request_payload or {}, ensure_ascii=False),
                created_by,
            )
        return int(value)

    async def mark_stage(self, job_id: int, stage: str) -> bool:
        cleaned = stage.strip()[:32]
        if not cleaned:
            raise ValueError("Этап AI-задания не может быть пустым.")
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE ai_jobs
                SET status = 'processing',
                    stage = $2::VARCHAR,
                    started_at = COALESCE(started_at, NOW()),
                    updated_at = NOW(),
                    error_message = NULL
                WHERE id = $1::BIGINT
                  AND status IN ('pending', 'processing')
                """,
                int(job_id),
                cleaned,
            )
        return result.endswith("1")

    async def mark_ready(
        self,
        job_id: int,
        *,
        result_text: str,
        result_payload: dict[str, Any] | None = None,
        reference_type: str | None = None,
        reference_id: int | None = None,
    ) -> bool:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE ai_jobs
                SET status = 'ready',
                    stage = 'completed',
                    result_text = $2::TEXT,
                    result_payload = $3::JSONB,
                    result_reference_type = $4::VARCHAR,
                    result_reference_id = $5::BIGINT,
                    error_message = NULL,
                    finished_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1::BIGINT
                """,
                int(job_id),
                result_text,
                json.dumps(result_payload, ensure_ascii=False) if result_payload is not None else None,
                reference_type[:48] if reference_type else None,
                int(reference_id) if reference_id is not None else None,
            )
        return result.endswith("1")

    async def mark_error(self, job_id: int, error: BaseException | str) -> bool:
        message = str(error).strip()[:3000] or "Неизвестная ошибка AI-задания."
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE ai_jobs
                SET status = 'error',
                    stage = 'failed',
                    error_message = $2::TEXT,
                    finished_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1::BIGINT
                  AND status <> 'ready'
                """,
                int(job_id),
                message,
            )
        return result.endswith("1")

    async def expire_stale(self, *, max_age_seconds: int = 1800) -> int:
        safe_age = max(300, min(int(max_age_seconds), 86_400))
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE ai_jobs
                SET status = 'error',
                    stage = 'interrupted',
                    error_message = COALESCE(
                        error_message,
                        'Задание было прервано перезапуском или превышением времени ожидания.'
                    ),
                    finished_at = NOW(),
                    updated_at = NOW()
                WHERE status IN ('pending', 'processing')
                  AND updated_at < NOW() - make_interval(secs => $1::INTEGER)
                """,
                safe_age,
            )
        return int(result.split()[-1])

    async def get(self, job_id: int, *, created_by: int | None = None) -> AIJob | None:
        await self.expire_stale()
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT *
                FROM ai_jobs
                WHERE id = $1::BIGINT
                  AND ($2::BIGINT IS NULL OR created_by = $2::BIGINT)
                """,
                int(job_id),
                created_by,
            )
        return self._from_row(row) if row is not None else None

    async def list_recent(
        self,
        *,
        created_by: int | None,
        page: int = 0,
        page_size: int = 8,
    ) -> AIJobPage:
        await self.expire_stale()
        safe_size = max(1, min(int(page_size), 12))
        async with self._database.acquire() as connection:
            total = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM ai_jobs
                    WHERE $1::BIGINT IS NULL OR created_by = $1::BIGINT
                    """,
                    created_by,
                )
                or 0
            )
            total_pages = max(1, (total + safe_size - 1) // safe_size)
            safe_page = min(max(0, int(page)), total_pages - 1)
            rows = await connection.fetch(
                """
                SELECT *
                FROM ai_jobs
                WHERE $1::BIGINT IS NULL OR created_by = $1::BIGINT
                ORDER BY created_at DESC, id DESC
                OFFSET $2::INTEGER LIMIT $3::INTEGER
                """,
                created_by,
                safe_page * safe_size,
                safe_size,
            )
        return AIJobPage(
            items=tuple(self._from_row(row) for row in rows),
            page=safe_page,
            page_size=safe_size,
            total_items=total,
        )


__all__ = (
    "AI_JOB_KINDS",
    "AI_JOB_STATUSES",
    "AIJob",
    "AIJobPage",
    "AIJobRepository",
)
