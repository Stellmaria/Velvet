from __future__ import annotations

import json
from typing import cast

from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage.librarian_content import redact_sensitive
from velvet_bot.domains.telegram_storage.librarian_models import (
    HermesRunResult,
    JsonObject,
    LibrarianAnalysis,
    LibrarianJob,
    LibrarianObject,
    LibrarianPart,
    StorageLibrarianSettings,
    UnsupportedStorageContent,
)


def _json_object(value: object) -> JsonObject:
    if isinstance(value, dict):
        return cast(JsonObject, dict(value))
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, dict):
            return cast(JsonObject, decoded)
    return {}


class StorageLibrarianRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def enqueue_pending(
        self,
        *,
        settings: StorageLibrarianSettings,
        limit: int = 200,
    ) -> int:
        if not settings.allowed_kinds:
            return 0
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                INSERT INTO telegram_storage_analysis_jobs (
                    storage_object_id, priority, max_attempts
                )
                SELECT
                    o.id,
                    CASE o.storage_kind
                        WHEN 'diagnostics' THEN 90
                        WHEN 'codex' THEN 80
                        WHEN 'rework' THEN 70
                        WHEN 'inbox' THEN 60
                        WHEN 'exports' THEN 50
                        WHEN 'releases' THEN 40
                        ELSE 0
                    END,
                    $4::INTEGER
                FROM telegram_storage_objects AS o
                LEFT JOIN telegram_storage_analysis AS a
                  ON a.storage_object_id = o.id
                WHERE o.storage_kind = ANY($1::VARCHAR[])
                  AND o.encrypted = FALSE
                  AND o.size_bytes <= $2::BIGINT
                  AND (
                      a.storage_object_id IS NULL
                      OR a.analyzer_version <> $3::TEXT
                  )
                ORDER BY o.migrated_at, o.id
                LIMIT $5::INTEGER
                ON CONFLICT (storage_object_id) DO UPDATE
                SET status = 'queued',
                    priority = EXCLUDED.priority,
                    attempts = 0,
                    max_attempts = EXCLUDED.max_attempts,
                    available_at = NOW(),
                    last_error = NULL,
                    locked_at = NULL,
                    worker_id = NULL,
                    hermes_run_id = NULL,
                    finished_at = NULL,
                    updated_at = NOW()
                WHERE telegram_storage_analysis_jobs.status IN ('completed', 'skipped')
                  AND EXISTS (
                      SELECT 1
                      FROM telegram_storage_analysis AS current_analysis
                      WHERE current_analysis.storage_object_id = EXCLUDED.storage_object_id
                        AND current_analysis.analyzer_version <> $3::TEXT
                  )
                """,
                list(settings.allowed_kinds),
                settings.max_object_bytes,
                settings.analyzer_version,
                settings.max_attempts,
                max(1, min(int(limit), 1000)),
            )
        return int(result.rsplit(" ", 1)[-1])

    async def enqueue_newer_than(
        self,
        *,
        settings: StorageLibrarianSettings,
        min_object_id: int,
        allowed_kinds: tuple[str, ...],
        limit: int = 1,
    ) -> int:
        kinds = tuple(
            kind
            for kind in allowed_kinds
            if kind in settings.allowed_kinds
        )
        if not kinds:
            return 0
        if int(min_object_id) <= 0:
            raise ValueError(
                "STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID должен быть больше нуля."
            )
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                INSERT INTO telegram_storage_analysis_jobs (
                    storage_object_id, priority, max_attempts
                )
                SELECT
                    o.id,
                    CASE o.storage_kind
                        WHEN 'diagnostics' THEN 90
                        WHEN 'codex' THEN 80
                        WHEN 'rework' THEN 70
                        WHEN 'inbox' THEN 60
                        WHEN 'exports' THEN 50
                        WHEN 'releases' THEN 40
                        ELSE 0
                    END,
                    $4::INTEGER
                FROM telegram_storage_objects AS o
                WHERE o.id > $1::BIGINT
                  AND o.storage_kind = ANY($2::VARCHAR[])
                  AND o.encrypted = FALSE
                  AND o.size_bytes <= $3::BIGINT
                  AND NOT EXISTS (
                      SELECT 1
                      FROM telegram_storage_analysis_jobs AS job
                      WHERE job.storage_object_id = o.id
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM telegram_storage_analysis AS analysis
                      WHERE analysis.storage_object_id = o.id
                  )
                ORDER BY o.id
                LIMIT $5::INTEGER
                ON CONFLICT (storage_object_id) DO NOTHING
                """,
                int(min_object_id),
                list(kinds),
                settings.max_object_bytes,
                settings.max_attempts,
                max(1, min(int(limit), 10)),
            )
        return int(result.rsplit(" ", 1)[-1])

    async def enqueue_object(
        self,
        object_id: int,
        *,
        settings: StorageLibrarianSettings,
        priority: int = 1000,
    ) -> bool:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT storage_kind, encrypted, size_bytes
                FROM telegram_storage_objects
                WHERE id = $1::BIGINT
                """,
                int(object_id),
            )
            if row is None:
                return False
            kind = str(row["storage_kind"])
            if (
                kind not in settings.allowed_kinds
                or bool(row["encrypted"])
                or int(row["size_bytes"]) > settings.max_object_bytes
            ):
                raise UnsupportedStorageContent(
                    f"Storage #{object_id} нельзя передать Librarian: kind={kind}."
                )
            await connection.execute(
                """
                INSERT INTO telegram_storage_analysis_jobs (
                    storage_object_id, status, priority, attempts,
                    max_attempts, available_at, last_error,
                    locked_at, worker_id, hermes_run_id,
                    finished_at, updated_at
                )
                VALUES (
                    $1::BIGINT, 'queued', $2::INTEGER, 0,
                    $3::INTEGER, NOW(), NULL,
                    NULL, NULL, NULL, NULL, NOW()
                )
                ON CONFLICT (storage_object_id) DO UPDATE
                SET status = 'queued',
                    priority = GREATEST(
                        telegram_storage_analysis_jobs.priority,
                        EXCLUDED.priority
                    ),
                    attempts = 0,
                    max_attempts = EXCLUDED.max_attempts,
                    available_at = NOW(),
                    last_error = NULL,
                    locked_at = NULL,
                    worker_id = NULL,
                    hermes_run_id = NULL,
                    finished_at = NULL,
                    updated_at = NOW()
                """,
                int(object_id),
                int(priority),
                settings.max_attempts,
            )
        return True

    async def claim_next(self, worker_id: str) -> LibrarianJob | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                WITH picked AS (
                    SELECT id
                    FROM telegram_storage_analysis_jobs
                    WHERE status = 'queued'
                      AND available_at <= NOW()
                      AND attempts < max_attempts
                    ORDER BY priority DESC, available_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE telegram_storage_analysis_jobs AS job
                SET status = 'running',
                    attempts = job.attempts + 1,
                    locked_at = NOW(),
                    worker_id = $1::TEXT,
                    updated_at = NOW()
                FROM picked
                WHERE job.id = picked.id
                UPDATE telegram_storage_analysis_jobs AS job
                SET status = 'running',
                    attempts = job.attempts + 1,
                    locked_at = NOW(),
                    worker_id = $1::TEXT,
                    updated_at = NOW()
                FROM picked
                WHERE job.id = picked.id
                RETURNING job.id, job.storage_object_id,
                          job.attempts, job.max_attempts
                """,
                worker_id,
            )
        if row is None:
            return None
        return LibrarianJob(
            job_id=int(row["id"]),
            storage_object_id=int(row["storage_object_id"]),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
        )

    async def load_object(self, object_id: int) -> LibrarianObject | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT id, storage_kind, logical_key, original_name,
                       mime_type, size_bytes, sha256, encrypted, manifest
                FROM telegram_storage_objects
                WHERE id = $1::BIGINT
                """,
                int(object_id),
            )
            if row is None:
                return None
            parts = await connection.fetch(
                """
                SELECT part_number, telegram_file_id, size_bytes, sha256
                FROM telegram_storage_parts
                WHERE storage_object_id = $1::BIGINT
                ORDER BY part_number
                """,
                int(object_id),
            )
        return LibrarianObject(
            object_id=int(row["id"]),
            storage_kind=str(row["storage_kind"]),
            logical_key=str(row["logical_key"]),
            original_name=str(row["original_name"]),
            mime_type=str(row["mime_type"]) if row["mime_type"] else None,
            size_bytes=int(row["size_bytes"]),
            sha256=str(row["sha256"]),
            encrypted=bool(row["encrypted"]),
            manifest=_json_object(row["manifest"]),
            parts=tuple(
                LibrarianPart(
                    part_number=int(part["part_number"]),
                    telegram_file_id=str(part["telegram_file_id"]),
                    size_bytes=int(part["size_bytes"]),
                    sha256=str(part["sha256"]),
                )
                for part in parts
            ),
        )

    async def complete(
        self,
        *,
        job: LibrarianJob,
        settings: StorageLibrarianSettings,
        analysis: LibrarianAnalysis,
        source_excerpt: str,
        run: HermesRunResult,
    ) -> None:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO telegram_storage_analysis (
                        storage_object_id, analyzer, analyzer_version, status,
                        summary, tags, entities, action_items, text_excerpt,
                        sensitivity, confidence, hermes_run_id, usage,
                        raw_response, error_message, analyzed_at, updated_at
                    )
                    VALUES (
                        $1::BIGINT, 'hermes', $2::TEXT, 'completed',
                        $3::TEXT, $4::JSONB, $5::JSONB, $6::JSONB, $7::TEXT,
                        $8::VARCHAR, $9::SMALLINT, $10::TEXT, $11::JSONB,
                        $12::JSONB, NULL, NOW(), NOW()
                    )
                    ON CONFLICT (storage_object_id) DO UPDATE
                    SET analyzer = EXCLUDED.analyzer,
                        analyzer_version = EXCLUDED.analyzer_version,
                        status = EXCLUDED.status,
                        summary = EXCLUDED.summary,
                        tags = EXCLUDED.tags,
                        entities = EXCLUDED.entities,
                        action_items = EXCLUDED.action_items,
                        text_excerpt = EXCLUDED.text_excerpt,
                        sensitivity = EXCLUDED.sensitivity,
                        confidence = EXCLUDED.confidence,
                        hermes_run_id = EXCLUDED.hermes_run_id,
                        usage = EXCLUDED.usage,
                        raw_response = EXCLUDED.raw_response,
                        error_message = NULL,
                        analyzed_at = NOW(),
                        updated_at = NOW()
                    """,
                    job.storage_object_id,
                    settings.analyzer_version,
                    analysis.summary,
                    json.dumps(analysis.tags, ensure_ascii=False),
                    json.dumps(analysis.entities, ensure_ascii=False),
                    json.dumps(analysis.action_items, ensure_ascii=False),
                    source_excerpt,
                    analysis.sensitivity,
                    analysis.confidence,
                    run.run_id,
                    json.dumps(run.usage, ensure_ascii=False),
                    json.dumps(analysis.raw, ensure_ascii=False),
                )
                await connection.execute(
                    """
                    UPDATE telegram_storage_analysis_jobs
                    SET status = 'completed',
                        hermes_run_id = $2::TEXT,
                        last_error = NULL,
                        locked_at = NULL,
                        worker_id = NULL,
                        finished_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $1::BIGINT
                    """,
                    job.job_id,
                    run.run_id,
                )

    async def skip(
        self,
        *,
        job: LibrarianJob,
        settings: StorageLibrarianSettings,
        reason: str,
    ) -> None:
        safe_reason = redact_sensitive(reason)[:2000]
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO telegram_storage_analysis (
                        storage_object_id, analyzer, analyzer_version, status,
                        summary, sensitivity, error_message,
                        analyzed_at, updated_at
                    )
                    VALUES (
                        $1::BIGINT, 'hermes', $2::TEXT, 'skipped',
                        '', 'restricted', $3::TEXT, NOW(), NOW()
                    )
                    ON CONFLICT (storage_object_id) DO UPDATE
                    SET analyzer = EXCLUDED.analyzer,
                        analyzer_version = EXCLUDED.analyzer_version,
                        status = EXCLUDED.status,
                        summary = '',
                        sensitivity = 'restricted',
                        error_message = EXCLUDED.error_message,
                        analyzed_at = NOW(),
                        updated_at = NOW()
                    """,
                    job.storage_object_id,
                    settings.analyzer_version,
                    safe_reason,
                )
                await connection.execute(
                    """
                    UPDATE telegram_storage_analysis_jobs
                    SET status = 'skipped',
                        last_error = $2::TEXT,
                        locked_at = NULL,
                        worker_id = NULL,
                        finished_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $1::BIGINT
                    """,
                    job.job_id,
                    safe_reason,
                )

    async def fail(self, job: LibrarianJob, error: BaseException) -> bool:
        message = redact_sensitive(str(error))[:2000]
        terminal = job.attempts >= job.max_attempts
        delay_seconds = min(1800, 60 * (2 ** max(0, job.attempts - 1)))
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE telegram_storage_analysis_jobs
                SET status = $2::VARCHAR,
                    available_at = CASE
                        WHEN $2::VARCHAR = 'queued'
                            THEN NOW() + ($3::INTEGER * INTERVAL '1 second')
                        ELSE available_at
                    END,
                    last_error = $4::TEXT,
                    locked_at = NULL,
                    worker_id = NULL,
                    finished_at = CASE
                        WHEN $2::VARCHAR = 'failed' THEN NOW()
                        ELSE NULL
                    END,
                    updated_at = NOW()
                WHERE id = $1::BIGINT
                """,
                job.job_id,
                "failed" if terminal else "queued",
                delay_seconds,
                message,
            )
        return terminal

    async def counts(self) -> dict[str, int]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT status, COUNT(*)::BIGINT AS count
                FROM telegram_storage_analysis_jobs
                GROUP BY status
                """
            )
        result = {
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
        }
        result.update({str(row["status"]): int(row["count"]) for row in rows})
        return result

    async def analysis_by_object_id(
        self,
        object_id: int,
    ) -> dict[str, object] | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT a.storage_object_id, a.summary, a.tags, a.entities,
                       a.action_items, a.sensitivity, a.confidence,
                       a.analyzed_at, a.analyzer_version,
                       o.storage_kind, o.logical_key, o.original_name
                FROM telegram_storage_analysis AS a
                JOIN telegram_storage_objects AS o
                  ON o.id = a.storage_object_id
                WHERE a.storage_object_id = $1::BIGINT
                  AND a.status = 'completed'
                """,
                int(object_id),
            )
        return dict(row) if row is not None else None

    async def recent_analyses(
        self,
        *,
        days: int = 1,
        limit: int = 12,
    ) -> list[dict[str, object]]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT a.storage_object_id, a.summary, a.tags, a.entities,
                       a.action_items, a.sensitivity, a.confidence,
                       a.analyzed_at, o.storage_kind, o.logical_key,
                       o.original_name
                FROM telegram_storage_analysis AS a
                JOIN telegram_storage_objects AS o
                  ON o.id = a.storage_object_id
                WHERE a.status = 'completed'
                  AND a.analyzed_at >= NOW() - ($1::INTEGER * INTERVAL '1 day')
                ORDER BY a.analyzed_at DESC, a.storage_object_id DESC
                LIMIT $2::INTEGER
                """,
                max(1, min(int(days), 365)),
                max(1, min(int(limit), 50)),
            )
        return [dict(row) for row in rows]

    async def search_analyses(
        self,
        query: str,
        *,
        limit: int = 8,
    ) -> list[dict[str, object]]:
        pattern = f"%{query.strip()}%"
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT a.storage_object_id, a.summary, a.tags, a.entities,
                       a.action_items, a.sensitivity, a.confidence,
                       a.analyzed_at, o.storage_kind, o.logical_key,
                       o.original_name
                FROM telegram_storage_analysis AS a
                JOIN telegram_storage_objects AS o
                  ON o.id = a.storage_object_id
                WHERE a.status = 'completed'
                  AND (
                      a.summary ILIKE $1::TEXT
                      OR a.tags::TEXT ILIKE $1::TEXT
                      OR a.entities::TEXT ILIKE $1::TEXT
                      OR a.action_items::TEXT ILIKE $1::TEXT
                      OR o.logical_key ILIKE $1::TEXT
                      OR o.original_name ILIKE $1::TEXT
                  )
                ORDER BY a.analyzed_at DESC, a.storage_object_id DESC
                LIMIT $2::INTEGER
                """,
                pattern,
                max(1, min(int(limit), 20)),
            )
        return [dict(row) for row in rows]


__all__ = ("StorageLibrarianRepository",)
