from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage.models import (
    MigrationSummary,
    StorageCandidate,
    StoredObject,
    StoredPart,
    StorageKind,
)


@dataclass(frozen=True, slots=True)
class WatermarkBackfillItem:
    media_id: int
    telegram_file_id: str
    telegram_file_unique_id: str | None
    file_size: int | None
    file_name: str
    character_names: tuple[str, ...]
    job_id: int | None
    revision: int | None
    source_path: Path | None
    final_path: Path | None


@dataclass(frozen=True, slots=True)
class BackupBackfillItem:
    run_id: int | None
    backup_kind: str
    path: Path
    file_name: str
    sha256: str | None
    schema_version: str | None
    validation: dict[str, Any]


@dataclass(frozen=True, slots=True)
class WatermarkCleanupItem:
    media_id: int | None
    job_id: int
    source_path: Path
    final_path: Path | None
    revision_paths: tuple[Path, ...]


class TelegramStorageRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def start_run(self, migration_kind: str, requested_by: int | None) -> int:
        async with self._database.acquire() as connection:
            return int(
                await connection.fetchval(
                    """
                    INSERT INTO telegram_storage_migration_runs (
                        migration_kind, status, requested_by
                    )
                    VALUES ($1::VARCHAR, 'running', $2::BIGINT)
                    RETURNING id
                    """,
                    migration_kind,
                    requested_by,
                )
            )

    async def finish_run(self, summary: MigrationSummary) -> None:
        details = json.dumps(
            {"by_kind": summary.by_kind, "errors": summary.errors[-100:]},
            ensure_ascii=False,
        )
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE telegram_storage_migration_runs
                SET status = $2::VARCHAR,
                    discovered_files = $3::INTEGER,
                    stored_files = $4::INTEGER,
                    skipped_files = $5::INTEGER,
                    failed_files = $6::INTEGER,
                    deleted_files = $7::INTEGER,
                    freed_bytes = $8::BIGINT,
                    details = $9::JSONB,
                    finished_at = NOW()
                WHERE id = $1::BIGINT
                """,
                summary.run_id,
                summary.status,
                summary.discovered_files,
                summary.stored_files,
                summary.skipped_files,
                summary.failed_files,
                summary.deleted_files,
                summary.freed_bytes,
                details,
            )

    async def initial_run_completed(self) -> bool:
        async with self._database.acquire() as connection:
            return bool(
                await connection.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM telegram_storage_migration_runs
                        WHERE migration_kind = 'initial_full'
                          AND status IN ('completed', 'partial')
                    )
                    """
                )
            )

    async def get_existing(
        self,
        kind: StorageKind,
        logical_key: str,
        sha256: str,
    ) -> StoredObject | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT id, storage_kind, logical_key, sha256, size_bytes,
                       chat_id, thread_id
                FROM telegram_storage_objects
                WHERE storage_kind = $1::VARCHAR
                  AND logical_key = $2::TEXT
                  AND sha256 = $3::CHAR(64)
                """,
                kind,
                logical_key,
                sha256,
            )
            if row is None:
                return None
            part_rows = await connection.fetch(
                """
                SELECT part_number, message_id, telegram_file_id,
                       telegram_file_unique_id, size_bytes, sha256
                FROM telegram_storage_parts
                WHERE storage_object_id = $1::BIGINT
                ORDER BY part_number
                """,
                int(row["id"]),
            )
        return StoredObject(
            object_id=int(row["id"]),
            kind=str(row["storage_kind"]),
            logical_key=str(row["logical_key"]),
            sha256=str(row["sha256"]),
            size_bytes=int(row["size_bytes"]),
            chat_id=int(row["chat_id"]),
            thread_id=int(row["thread_id"]),
            parts=tuple(
                StoredPart(
                    part_number=int(part["part_number"]),
                    message_id=int(part["message_id"]),
                    telegram_file_id=str(part["telegram_file_id"]),
                    telegram_file_unique_id=(
                        str(part["telegram_file_unique_id"])
                        if part["telegram_file_unique_id"] is not None
                        else None
                    ),
                    size_bytes=int(part["size_bytes"]),
                    sha256=str(part["sha256"]),
                )
                for part in part_rows
            ),
        )

    async def create_object(
        self,
        *,
        candidate: StorageCandidate,
        sha256: str,
        size_bytes: int,
        chat_id: int,
        thread_id: int,
        parts: tuple[StoredPart, ...],
        manifest: dict[str, Any],
        encryption_version: str | None,
    ) -> StoredObject:
        payload = json.dumps(manifest, ensure_ascii=False)
        async with self._database.acquire() as connection:
            async with connection.transaction():
                object_id = int(
                    await connection.fetchval(
                        """
                        INSERT INTO telegram_storage_objects (
                            storage_kind, logical_key, original_name, source_path,
                            mime_type, size_bytes, sha256, encrypted,
                            encryption_version, chat_id, thread_id, part_count,
                            manifest
                        )
                        VALUES (
                            $1::VARCHAR, $2::TEXT, $3::TEXT, $4::TEXT,
                            $5::TEXT, $6::BIGINT, $7::CHAR(64), $8::BOOLEAN,
                            $9::TEXT, $10::BIGINT, $11::BIGINT, $12::INTEGER,
                            $13::JSONB
                        )
                        ON CONFLICT (storage_kind, logical_key, sha256)
                        DO UPDATE SET manifest = EXCLUDED.manifest
                        RETURNING id
                        """,
                        candidate.kind,
                        candidate.logical_key,
                        candidate.original_name,
                        candidate.source_path,
                        candidate.mime_type,
                        int(size_bytes),
                        sha256,
                        candidate.encrypted,
                        encryption_version,
                        int(chat_id),
                        int(thread_id),
                        len(parts),
                        payload,
                    )
                )
                await connection.execute(
                    "DELETE FROM telegram_storage_parts WHERE storage_object_id = $1::BIGINT",
                    object_id,
                )
                await connection.executemany(
                    """
                    INSERT INTO telegram_storage_parts (
                        storage_object_id, part_number, message_id,
                        telegram_file_id, telegram_file_unique_id,
                        size_bytes, sha256
                    )
                    VALUES (
                        $1::BIGINT, $2::INTEGER, $3::BIGINT,
                        $4::TEXT, $5::TEXT, $6::BIGINT, $7::CHAR(64)
                    )
                    """,
                    [
                        (
                            object_id,
                            part.part_number,
                            part.message_id,
                            part.telegram_file_id,
                            part.telegram_file_unique_id,
                            part.size_bytes,
                            part.sha256,
                        )
                        for part in parts
                    ],
                )
        return StoredObject(
            object_id=object_id,
            kind=candidate.kind,
            logical_key=candidate.logical_key,
            sha256=sha256,
            size_bytes=size_bytes,
            chat_id=chat_id,
            thread_id=thread_id,
            parts=parts,
        )

    async def mark_local_deleted(self, object_id: int) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE telegram_storage_objects
                SET local_deleted_at = NOW()
                WHERE id = $1::BIGINT
                """,
                int(object_id),
            )

    async def list_objects(
        self,
        *,
        kind: StorageKind | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 100))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT o.id, o.storage_kind, o.logical_key, o.original_name,
                       o.size_bytes, o.sha256, o.encrypted, o.chat_id,
                       o.thread_id, o.part_count, o.migrated_at,
                       o.local_deleted_at,
                       MIN(p.message_id) AS first_message_id
                FROM telegram_storage_objects AS o
                LEFT JOIN telegram_storage_parts AS p
                  ON p.storage_object_id = o.id
                WHERE ($1::VARCHAR IS NULL OR o.storage_kind = $1::VARCHAR)
                GROUP BY o.id
                ORDER BY o.migrated_at DESC, o.id DESC
                LIMIT $2::INTEGER
                """,
                kind,
                safe_limit,
            )
        return [dict(row) for row in rows]

    async def list_watermarks_for_backfill(self, limit: int = 500) -> list[WatermarkBackfillItem]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    mf.id AS media_id,
                    mf.telegram_file_id,
                    mf.telegram_file_unique_id,
                    mf.file_size,
                    COALESCE(mf.original_file_name, mf.storage_file_name) AS file_name,
                    ARRAY_REMOVE(
                        ARRAY_AGG(DISTINCT c.name ORDER BY c.name),
                        NULL
                    ) AS character_names,
                    job.id AS job_id,
                    job.current_revision,
                    job.source_path,
                    job.final_path
                FROM media_files AS mf
                LEFT JOIN character_media AS cm ON cm.media_id = mf.id
                LEFT JOIN characters AS c ON c.id = cm.character_id
                LEFT JOIN LATERAL (
                    SELECT wj.id, wj.current_revision, wj.source_path, wj.final_path
                    FROM watermark_jobs AS wj
                    WHERE wj.source_message_id = -mf.id
                      AND wj.status = 'approved'
                    ORDER BY wj.updated_at DESC, wj.id DESC
                    LIMIT 1
                ) AS job ON TRUE
                WHERE mf.watermark_approved = TRUE
                  AND mf.watermark_storage_message_id IS NULL
                  AND mf.telegram_file_id IS NOT NULL
                GROUP BY mf.id, job.id, job.current_revision,
                         job.source_path, job.final_path
                ORDER BY mf.id
                LIMIT $1::INTEGER
                """,
                max(1, min(int(limit), 5000)),
            )
        return [
            WatermarkBackfillItem(
                media_id=int(row["media_id"]),
                telegram_file_id=str(row["telegram_file_id"]),
                telegram_file_unique_id=(
                    str(row["telegram_file_unique_id"])
                    if row["telegram_file_unique_id"] is not None
                    else None
                ),
                file_size=int(row["file_size"]) if row["file_size"] is not None else None,
                file_name=str(row["file_name"]),
                character_names=tuple(str(value) for value in (row["character_names"] or ())),
                job_id=int(row["job_id"]) if row["job_id"] is not None else None,
                revision=(
                    int(row["current_revision"])
                    if row["current_revision"] is not None
                    else None
                ),
                source_path=Path(row["source_path"]) if row["source_path"] else None,
                final_path=Path(row["final_path"]) if row["final_path"] else None,
            )
            for row in rows
        ]

    async def mark_watermark_backfilled(
        self,
        *,
        media_id: int,
        chat_id: int,
        thread_id: int,
        message_id: int,
        telegram_file_id: str,
        telegram_file_unique_id: str | None,
        file_size: int,
        sha256: str | None,
    ) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE media_files
                SET telegram_file_id = $2::TEXT,
                    telegram_file_unique_id = COALESCE($3::TEXT, telegram_file_unique_id),
                    file_size = $4::BIGINT,
                    watermark_storage_chat_id = $5::BIGINT,
                    watermark_storage_thread_id = $6::BIGINT,
                    watermark_storage_message_id = $7::BIGINT,
                    watermark_storage_file_id = $2::TEXT,
                    watermark_storage_file_unique_id = $3::TEXT,
                    watermark_storage_file_size = $4::BIGINT,
                    watermark_storage_sha256 = $8::CHAR(64),
                    watermark_stored_at = NOW()
                WHERE id = $1::BIGINT
                """,
                int(media_id),
                telegram_file_id,
                telegram_file_unique_id,
                int(file_size),
                int(chat_id),
                int(thread_id),
                int(message_id),
                sha256,
            )

    async def mark_watermark_cleaned(self, media_id: int) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE media_files
                SET watermark_local_cleaned_at = NOW()
                WHERE id = $1::BIGINT
                """,
                int(media_id),
            )

    async def list_watermark_cleanup_items(self) -> list[WatermarkCleanupItem]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT wj.id AS job_id,
                       CASE WHEN wj.source_message_id < 0
                            THEN -wj.source_message_id ELSE NULL END AS media_id,
                       wj.source_path,
                       wj.final_path,
                       ARRAY_REMOVE(
                           ARRAY_AGG(DISTINCT path_value), NULL
                       ) AS revision_paths
                FROM watermark_jobs AS wj
                LEFT JOIN watermark_revisions AS wr ON wr.job_id = wj.id
                LEFT JOIN LATERAL unnest(ARRAY[
                    wr.request_path,
                    wr.output_path,
                    wr.response_path
                ]) AS path_value ON TRUE
                WHERE wj.status IN ('approved', 'cancelled')
                GROUP BY wj.id
                ORDER BY wj.id
                """
            )
        return [
            WatermarkCleanupItem(
                media_id=int(row["media_id"]) if row["media_id"] is not None else None,
                job_id=int(row["job_id"]),
                source_path=Path(row["source_path"]),
                final_path=Path(row["final_path"]) if row["final_path"] else None,
                revision_paths=tuple(Path(value) for value in (row["revision_paths"] or ())),
            )
            for row in rows
        ]

    async def list_backup_backfill(self, backup_dir: Path) -> list[BackupBackfillItem]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT id, backup_kind, file_path, file_name, sha256,
                       schema_version, validation
                FROM backup_runs
                WHERE status = 'valid'
                  AND file_path IS NOT NULL
                  AND telegram_storage_object_id IS NULL
                ORDER BY started_at, id
                """
            )
        found: list[BackupBackfillItem] = []
        known: set[Path] = set()
        for row in rows:
            path = Path(str(row["file_path"])).expanduser().resolve()
            if not path.is_file():
                continue
            known.add(path)
            found.append(
                BackupBackfillItem(
                    run_id=int(row["id"]),
                    backup_kind=str(row["backup_kind"]),
                    path=path,
                    file_name=str(row["file_name"] or path.name),
                    sha256=str(row["sha256"]) if row["sha256"] else None,
                    schema_version=str(row["schema_version"]) if row["schema_version"] else None,
                    validation=dict(row["validation"] or {}),
                )
            )
        if backup_dir.is_dir():
            for path in sorted(backup_dir.glob("*.dump")):
                resolved = path.resolve()
                if resolved in known or not resolved.is_file():
                    continue
                found.append(
                    BackupBackfillItem(
                        run_id=None,
                        backup_kind="untracked",
                        path=resolved,
                        file_name=resolved.name,
                        sha256=None,
                        schema_version=None,
                        validation={},
                    )
                )
        return found

    async def mark_backup_offloaded(self, run_id: int, object_id: int) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE backup_runs
                SET telegram_storage_object_id = $2::BIGINT,
                    offloaded_at = NOW(),
                    file_path = NULL
                WHERE id = $1::BIGINT
                """,
                int(run_id),
                int(object_id),
            )

    async def rework_snapshot(self) -> list[dict[str, Any]]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT r.media_id, r.status, r.source, r.reason, r.qwen_score,
                       r.requested_by, r.created_at, r.updated_at,
                       mf.original_file_name, mf.storage_file_name,
                       mf.telegram_file_id,
                       mf.watermark_storage_chat_id,
                       mf.watermark_storage_message_id
                FROM media_rework_items AS r
                JOIN media_files AS mf ON mf.id = r.media_id
                WHERE r.status NOT IN ('accepted', 'removed')
                ORDER BY r.updated_at DESC, r.media_id
                """
            )
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for key in ("created_at", "updated_at"):
                if item.get(key) is not None:
                    item[key] = item[key].isoformat()
            result.append(item)
        return result


__all__ = (
    "BackupBackfillItem",
    "TelegramStorageRepository",
    "WatermarkBackfillItem",
    "WatermarkCleanupItem",
)
