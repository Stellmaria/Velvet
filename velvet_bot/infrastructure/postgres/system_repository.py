from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from velvet_bot.database import Database


@dataclass(frozen=True, slots=True)
class RuntimeDatabaseSnapshot:
    database_name: str
    postgres_version: str
    database_size_bytes: int
    schema_version: str | None
    migration_count: int
    character_count: int
    media_count: int
    tracked_channel_count: int
    tracked_discussion_count: int
    scheduled_publications: int
    publishing_publications: int
    publication_errors: int
    pending_visual_scans: int
    unknown_file_checks: int
    latest_backup_status: str | None
    latest_backup_at: datetime | None
    latest_backup_file_name: str | None


class SystemRepository:
    """Read-only PostgreSQL boundary for runtime diagnostics."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def ping(self) -> None:
        async with self.database.acquire() as connection:
            await connection.fetchval("SELECT 1")

    async def get_runtime_snapshot(self) -> RuntimeDatabaseSnapshot:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    current_database() AS database_name,
                    current_setting('server_version') AS postgres_version,
                    pg_database_size(current_database()) AS database_size_bytes,
                    (
                        SELECT version
                        FROM schema_migrations
                        ORDER BY version DESC
                        LIMIT 1
                    ) AS schema_version,
                    (SELECT COUNT(*) FROM schema_migrations) AS migration_count,
                    (SELECT COUNT(*) FROM characters) AS character_count,
                    (SELECT COUNT(*) FROM media_files) AS media_count,
                    (
                        SELECT COUNT(*)
                        FROM tracked_channels
                        WHERE source_kind = 'channel' AND enabled = TRUE
                    ) AS tracked_channel_count,
                    (
                        SELECT COUNT(*)
                        FROM tracked_channels
                        WHERE source_kind = 'discussion' AND enabled = TRUE
                    ) AS tracked_discussion_count,
                    (
                        SELECT COUNT(*)
                        FROM publication_drafts
                        WHERE status = 'scheduled'
                    ) AS scheduled_publications,
                    (
                        SELECT COUNT(*)
                        FROM publication_drafts
                        WHERE status = 'publishing'
                    ) AS publishing_publications,
                    (
                        SELECT COUNT(*)
                        FROM publication_drafts
                        WHERE status = 'error'
                    ) AS publication_errors,
                    (
                        SELECT COUNT(*)
                        FROM media_files
                        WHERE visual_scan_status IN ('pending', 'processing')
                    ) AS pending_visual_scans,
                    (
                        SELECT COUNT(*)
                        FROM media_file_checks
                        WHERE status = 'unknown'
                    ) AS unknown_file_checks,
                    (
                        SELECT status
                        FROM backup_runs
                        ORDER BY started_at DESC, id DESC
                        LIMIT 1
                    ) AS latest_backup_status,
                    (
                        SELECT COALESCE(finished_at, started_at)
                        FROM backup_runs
                        ORDER BY started_at DESC, id DESC
                        LIMIT 1
                    ) AS latest_backup_at,
                    (
                        SELECT file_name
                        FROM backup_runs
                        ORDER BY started_at DESC, id DESC
                        LIMIT 1
                    ) AS latest_backup_file_name
                """
            )
        if row is None:
            raise RuntimeError("PostgreSQL не вернул системную сводку.")
        return RuntimeDatabaseSnapshot(
            database_name=str(row["database_name"]),
            postgres_version=str(row["postgres_version"]),
            database_size_bytes=int(row["database_size_bytes"] or 0),
            schema_version=(
                str(row["schema_version"])
                if row["schema_version"] is not None
                else None
            ),
            migration_count=int(row["migration_count"] or 0),
            character_count=int(row["character_count"] or 0),
            media_count=int(row["media_count"] or 0),
            tracked_channel_count=int(row["tracked_channel_count"] or 0),
            tracked_discussion_count=int(row["tracked_discussion_count"] or 0),
            scheduled_publications=int(row["scheduled_publications"] or 0),
            publishing_publications=int(row["publishing_publications"] or 0),
            publication_errors=int(row["publication_errors"] or 0),
            pending_visual_scans=int(row["pending_visual_scans"] or 0),
            unknown_file_checks=int(row["unknown_file_checks"] or 0),
            latest_backup_status=(
                str(row["latest_backup_status"])
                if row["latest_backup_status"] is not None
                else None
            ),
            latest_backup_at=row["latest_backup_at"],
            latest_backup_file_name=(
                str(row["latest_backup_file_name"])
                if row["latest_backup_file_name"] is not None
                else None
            ),
        )
