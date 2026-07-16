from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from velvet_bot.backup_service import (
    BackupError,
    BackupRecord,
    BackupService as BaseBackupService,
    BackupValidation,
)
from velvet_bot.database import Database

logger = logging.getLogger(__name__)
_MISSING_PG_DUMP_PREFIX = "Не найден pg_dump."


def _decode_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _is_missing_pg_dump_error(error: BaseException) -> bool:
    return str(error).startswith(_MISSING_PG_DUMP_PREFIX)


class BackupService(BaseBackupService):
    """Runtime-hardened backup service used by the bot entrypoint."""

    def _warn_missing_pg_dump_once(self, *, context: str, error: BackupError) -> None:
        if getattr(self, "_missing_pg_dump_warning_emitted", False):
            return
        self._missing_pg_dump_warning_emitted = True
        logger.warning(
            "%s skipped because pg_dump is unavailable. "
            "The bot will continue without automatic PostgreSQL backups: %s",
            context,
            error,
        )

    async def prepare_pre_migration_backup(self) -> bool:
        """Skip only the optional startup backup when pg_dump is unavailable."""
        try:
            return await super().prepare_pre_migration_backup()
        except BackupError as error:
            if not _is_missing_pg_dump_error(error):
                raise
            self._warn_missing_pg_dump_once(
                context="Pre-migration backup",
                error=error,
            )
            return False

    @staticmethod
    def _row_to_record(row: Any) -> BackupRecord:
        validation = _decode_json(row["validation"], {})
        if not isinstance(validation, dict):
            validation = {}
        return BackupRecord(
            id=int(row["id"]),
            backup_kind=str(row["backup_kind"]),
            status=str(row["status"]),
            file_name=row["file_name"],
            file_path=row["file_path"],
            size_bytes=(
                int(row["size_bytes"]) if row["size_bytes"] is not None else None
            ),
            sha256=row["sha256"],
            schema_version=row["schema_version"],
            created_by=(
                int(row["created_by"]) if row["created_by"] is not None else None
            ),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            error_message=row["error_message"],
            validation=validation,
        )

    async def _expected_tables_for_record(
        self,
        database: Database,
        backup_id: int,
    ) -> tuple[str, ...]:
        async with database._require_pool().acquire() as connection:
            value = await connection.fetchval(
                "SELECT expected_tables FROM backup_runs WHERE id = $1::BIGINT",
                int(backup_id),
            )
        decoded = _decode_json(value, [])
        if not isinstance(decoded, list):
            return ()
        return tuple(str(item) for item in decoded)

    async def _create_dump_file(
        self,
        *,
        backup_kind: str,
        expected_tables: tuple[str, ...],
        schema_version: str | None,
        current_schema_version: str | None,
        created_by: int | None,
        extra_manifest: dict[str, Any] | None = None,
    ) -> tuple[Path, BackupValidation]:
        if backup_kind not in {"manual", "daily", "weekly", "pre_migration"}:
            raise BackupError("Неизвестный тип резервной копии.")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        pg_dump = self._executable(self.pg_dump_path, "pg_dump")
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        schema_label = (schema_version or "fresh").replace(".sql", "")
        final_path = self.backup_dir / (
            f"velvet_{backup_kind}_{stamp}_{schema_label}.dump"
        )
        temporary_path = final_path.with_suffix(".dump.part")
        temporary_path.unlink(missing_ok=True)

        return_code, _, stderr = await self._run_process(
            pg_dump,
            "--format=custom",
            "--compress=6",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(temporary_path),
            "--dbname",
            self.database_url,
        )
        if return_code != 0:
            temporary_path.unlink(missing_ok=True)
            raise BackupError(stderr.strip() or "pg_dump завершился с ошибкой.")
        if not temporary_path.is_file() or temporary_path.stat().st_size <= 0:
            temporary_path.unlink(missing_ok=True)
            raise BackupError("pg_dump не создал непустой файл резервной копии.")
        temporary_path.replace(final_path)
        try:
            validation = await self._validate_dump(
                final_path,
                expected_tables=expected_tables,
                schema_version=schema_version,
                current_schema_version=current_schema_version,
            )
            self._write_manifest(
                final_path,
                backup_kind=backup_kind,
                validation=validation,
                created_by=created_by,
                extra=extra_manifest,
            )
        except Exception:
            final_path.unlink(missing_ok=True)
            self._manifest_path(final_path).unlink(missing_ok=True)
            raise
        return final_path, validation

    async def _ran_kind_today(
        self,
        database: Database,
        *,
        local_now: datetime,
        timezone_name: str,
        backup_kinds: tuple[str, ...],
    ) -> bool:
        async with database._require_pool().acquire() as connection:
            return bool(
                await connection.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM backup_runs
                        WHERE backup_kind = ANY($1::VARCHAR[])
                          AND status IN ('valid', 'invalid', 'running')
                          AND timezone($2::TEXT, started_at)::DATE = $3::DATE
                    )
                    """,
                    list(backup_kinds),
                    timezone_name,
                    local_now.date(),
                )
            )

    async def run_scheduled_if_due(self, database: Database) -> BackupRecord | None:
        settings = await self.get_settings(database)
        local_now = datetime.now(ZoneInfo(settings.timezone))
        weekly_due = (
            settings.weekly_enabled
            and local_now.weekday() == settings.weekly_weekday
            and local_now.hour >= settings.weekly_hour
            and not await self._ran_kind_today(
                database,
                local_now=local_now,
                timezone_name=settings.timezone,
                backup_kinds=("weekly",),
            )
        )
        if weekly_due:
            try:
                record = await self.create_backup(database, backup_kind="weekly")
            except BackupError as error:
                if not _is_missing_pg_dump_error(error):
                    raise
                self._warn_missing_pg_dump_once(
                    context="Scheduled PostgreSQL backup",
                    error=error,
                )
                return None
            await self.cleanup_old_backups(database)
            return record

        daily_due = (
            settings.daily_enabled
            and local_now.hour >= settings.daily_hour
            and not await self._ran_kind_today(
                database,
                local_now=local_now,
                timezone_name=settings.timezone,
                backup_kinds=("daily", "weekly"),
            )
        )
        if daily_due:
            try:
                record = await self.create_backup(database, backup_kind="daily")
            except BackupError as error:
                if not _is_missing_pg_dump_error(error):
                    raise
                self._warn_missing_pg_dump_once(
                    context="Scheduled PostgreSQL backup",
                    error=error,
                )
                return None
            await self.cleanup_old_backups(database)
            return record
        return None
