from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from velvet_bot.database import Database

logger = logging.getLogger(__name__)

_BACKUP_KINDS = frozenset({"manual", "daily", "weekly", "pre_migration"})
_TABLE_LINE_RE = re.compile(
    r"\bTABLE(?: DATA)?\s+public\s+([^\s]+)",
    re.IGNORECASE,
)


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BackupSettings:
    daily_enabled: bool
    daily_hour: int
    weekly_enabled: bool
    weekly_weekday: int
    weekly_hour: int
    retention_count: int
    timezone: str


@dataclass(frozen=True, slots=True)
class BackupValidation:
    valid: bool
    readable: bool
    size_bytes: int
    sha256: str | None
    expected_tables: tuple[str, ...]
    discovered_tables: tuple[str, ...]
    missing_tables: tuple[str, ...]
    schema_version: str | None
    current_schema_version: str | None
    schema_matches: bool
    message: str


@dataclass(frozen=True, slots=True)
class BackupRecord:
    id: int
    backup_kind: str
    status: str
    file_name: str | None
    file_path: str | None
    size_bytes: int | None
    sha256: str | None
    schema_version: str | None
    created_by: int | None
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None
    validation: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CleanupResult:
    deleted_files: int
    freed_bytes: int
    retained_files: int


def parse_pg_restore_tables(output: str) -> tuple[str, ...]:
    tables = {
        match.group(1).strip('"')
        for line in output.splitlines()
        if (match := _TABLE_LINE_RE.search(line))
    }
    return tuple(sorted(tables))


def select_retained_paths(
    records: list[tuple[int, str | None]],
    retention_count: int,
) -> tuple[set[int], set[int]]:
    safe_count = max(3, min(int(retention_count), 100))
    with_files = [(record_id, path) for record_id, path in records if path]
    kept = {record_id for record_id, _ in with_files[:safe_count]}
    deleted = {record_id for record_id, _ in with_files[safe_count:]}
    return kept, deleted


def _status_count(value: str) -> int:
    try:
        return int(value.rsplit(" ", 1)[-1])
    except (TypeError, ValueError):
        return 0


class BackupService:
    def __init__(
        self,
        *,
        database_url: str,
        backup_dir: str | Path,
        pg_dump_path: str = "pg_dump",
        pg_restore_path: str = "pg_restore",
        migrations_path: str | Path | None = None,
    ) -> None:
        self.database_url = database_url
        self.backup_dir = Path(backup_dir).expanduser().resolve()
        self.pg_dump_path = pg_dump_path
        self.pg_restore_path = pg_restore_path
        self.migrations_path = (
            Path(migrations_path)
            if migrations_path is not None
            else Path(__file__).resolve().parents[1] / "migrations"
        )
        self._pending_pre_migration: dict[str, Any] | None = None
        self._run_lock = asyncio.Lock()

    def _executable(self, configured: str, label: str) -> str:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        resolved = shutil.which(configured)
        if resolved:
            return resolved
        raise BackupError(
            f"Не найден {label}. Укажите путь в .env или добавьте утилиты "
            "PostgreSQL в PATH."
        )

    async def _run_process(self, *arguments: str) -> tuple[int, str, str]:
        process = await asyncio.create_subprocess_exec(
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        stdout, stderr = await process.communicate()
        return (
            int(process.returncode or 0),
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    @staticmethod
    async def _schema_version(connection: asyncpg.Connection) -> str | None:
        exists = await connection.fetchval(
            "SELECT to_regclass('public.schema_migrations') IS NOT NULL"
        )
        if not exists:
            return None
        value = await connection.fetchval(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        )
        return str(value) if value is not None else None

    @staticmethod
    async def _public_tables(connection: asyncpg.Connection) -> tuple[str, ...]:
        rows = await connection.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        return tuple(str(row["table_name"]) for row in rows)

    def _migration_versions(self) -> tuple[str, ...]:
        return tuple(path.name for path in sorted(self.migrations_path.glob("*.sql")))

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    async def _validate_dump(
        self,
        path: Path,
        *,
        expected_tables: tuple[str, ...],
        schema_version: str | None,
        current_schema_version: str | None,
    ) -> BackupValidation:
        if not path.is_file():
            return BackupValidation(
                valid=False,
                readable=False,
                size_bytes=0,
                sha256=None,
                expected_tables=expected_tables,
                discovered_tables=(),
                missing_tables=expected_tables,
                schema_version=schema_version,
                current_schema_version=current_schema_version,
                schema_matches=schema_version == current_schema_version,
                message="Файл резервной копии не найден.",
            )
        size = path.stat().st_size
        if size <= 0:
            return BackupValidation(
                valid=False,
                readable=False,
                size_bytes=size,
                sha256=None,
                expected_tables=expected_tables,
                discovered_tables=(),
                missing_tables=expected_tables,
                schema_version=schema_version,
                current_schema_version=current_schema_version,
                schema_matches=schema_version == current_schema_version,
                message="Файл резервной копии пустой.",
            )

        pg_restore = self._executable(self.pg_restore_path, "pg_restore")
        return_code, stdout, stderr = await self._run_process(
            pg_restore,
            "--list",
            str(path),
        )
        discovered = parse_pg_restore_tables(stdout)
        missing = tuple(sorted(set(expected_tables) - set(discovered)))
        readable = return_code == 0
        schema_matches = schema_version == current_schema_version
        valid = readable and not missing and schema_matches
        if not readable:
            message = stderr.strip() or "pg_restore не смог прочитать архив."
        elif missing:
            message = "В архиве отсутствуют таблицы: " + ", ".join(missing)
        elif not schema_matches:
            message = (
                "Версия схемы копии не совпадает с текущей: "
                f"{schema_version or 'нет'} → {current_schema_version or 'нет'}."
            )
        else:
            message = "Архив читается, таблицы и версия схемы совпадают."
        return BackupValidation(
            valid=valid,
            readable=readable,
            size_bytes=size,
            sha256=self._sha256(path),
            expected_tables=expected_tables,
            discovered_tables=discovered,
            missing_tables=missing,
            schema_version=schema_version,
            current_schema_version=current_schema_version,
            schema_matches=schema_matches,
            message=message[:2000],
        )

    @staticmethod
    def _validation_dict(validation: BackupValidation) -> dict[str, Any]:
        return {
            "valid": validation.valid,
            "readable": validation.readable,
            "schema_matches": validation.schema_matches,
            "message": validation.message,
            "missing_tables": list(validation.missing_tables),
            "checked_at": datetime.now(UTC).isoformat(),
        }

    def _manifest_path(self, dump_path: Path) -> Path:
        return dump_path.with_suffix(dump_path.suffix + ".json")

    def _write_manifest(
        self,
        dump_path: Path,
        *,
        backup_kind: str,
        validation: BackupValidation,
        created_by: int | None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "backup_kind": backup_kind,
            "file_name": dump_path.name,
            "file_path": str(dump_path),
            "size_bytes": validation.size_bytes,
            "sha256": validation.sha256,
            "schema_version": validation.schema_version,
            "expected_tables": list(validation.expected_tables),
            "discovered_tables": list(validation.discovered_tables),
            "validation": self._validation_dict(validation),
            "created_by": created_by,
            "created_at": datetime.now(UTC).isoformat(),
        }
        if extra:
            payload.update(extra)
        self._manifest_path(dump_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
        if backup_kind not in _BACKUP_KINDS:
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
        return final_path, validation

    async def prepare_pre_migration_backup(self) -> bool:
        connection = await asyncpg.connect(self.database_url, command_timeout=60)
        try:
            current_version = await self._schema_version(connection)
            expected_tables = await self._public_tables(connection)
            if not expected_tables:
                return False
            applied: set[str] = set()
            if current_version is not None:
                rows = await connection.fetch("SELECT version FROM schema_migrations")
                applied = {str(row["version"]) for row in rows}
            pending = tuple(
                version
                for version in self._migration_versions()
                if version not in applied
            )
            user_tables = tuple(
                table for table in expected_tables if table != "schema_migrations"
            )
            if not pending or not user_tables:
                return False
            async with self._run_lock:
                path, validation = await self._create_dump_file(
                    backup_kind="pre_migration",
                    expected_tables=expected_tables,
                    schema_version=current_version,
                    current_schema_version=current_version,
                    created_by=None,
                    extra_manifest={"pending_migrations": list(pending)},
                )
            if not validation.valid:
                raise BackupError(
                    "Предмиграционная копия не прошла проверку: "
                    + validation.message
                )
            self._pending_pre_migration = {
                "path": path,
                "validation": validation,
                "pending_migrations": pending,
            }
            return True
        finally:
            await connection.close()

    async def persist_pre_migration_backup(self, database: Database) -> None:
        pending = self._pending_pre_migration
        if pending is None:
            return
        path: Path = pending["path"]
        validation: BackupValidation = pending["validation"]
        await self._insert_completed_run(
            database,
            backup_kind="pre_migration",
            path=path,
            validation=validation,
            created_by=None,
            validation_extra={
                "pending_migrations": list(pending["pending_migrations"]),
            },
        )
        self._pending_pre_migration = None

    async def _insert_running_run(
        self,
        database: Database,
        *,
        backup_kind: str,
        created_by: int | None,
    ) -> int:
        async with database.acquire() as connection:
            return int(
                await connection.fetchval(
                    """
                    INSERT INTO backup_runs (backup_kind, status, created_by)
                    VALUES ($1::VARCHAR, 'running', $2::BIGINT)
                    RETURNING id
                    """,
                    backup_kind,
                    created_by,
                )
            )

    async def _insert_completed_run(
        self,
        database: Database,
        *,
        backup_kind: str,
        path: Path,
        validation: BackupValidation,
        created_by: int | None,
        validation_extra: dict[str, Any] | None = None,
    ) -> int:
        details = self._validation_dict(validation)
        if validation_extra:
            details.update(validation_extra)
        async with database.acquire() as connection:
            return int(
                await connection.fetchval(
                    """
                    INSERT INTO backup_runs (
                        backup_kind, status, file_name, file_path, size_bytes,
                        sha256, schema_version, expected_tables,
                        discovered_tables, validation, created_by,
                        finished_at, error_message
                    )
                    VALUES (
                        $1::VARCHAR, $2::VARCHAR, $3::TEXT, $4::TEXT, $5::BIGINT,
                        $6::CHAR(64), $7::TEXT, $8::JSONB,
                        $9::JSONB, $10::JSONB, $11::BIGINT,
                        NOW(), $12::TEXT
                    )
                    RETURNING id
                    """,
                    backup_kind,
                    "valid" if validation.valid else "invalid",
                    path.name,
                    str(path),
                    validation.size_bytes,
                    validation.sha256,
                    validation.schema_version,
                    json.dumps(validation.expected_tables, ensure_ascii=False),
                    json.dumps(validation.discovered_tables, ensure_ascii=False),
                    json.dumps(details, ensure_ascii=False),
                    created_by,
                    None if validation.valid else validation.message,
                )
            )

    async def create_backup(
        self,
        database: Database,
        *,
        backup_kind: str,
        created_by: int | None = None,
    ) -> BackupRecord:
        if backup_kind not in _BACKUP_KINDS - {"pre_migration"}:
            raise BackupError("Недоступный тип ручного резервирования.")
        async with self._run_lock:
            run_id = await self._insert_running_run(
                database,
                backup_kind=backup_kind,
                created_by=created_by,
            )
            try:
                async with database.acquire() as connection:
                    schema_version = await self._schema_version(connection)
                    expected_tables = await self._public_tables(connection)
                path, validation = await self._create_dump_file(
                    backup_kind=backup_kind,
                    expected_tables=expected_tables,
                    schema_version=schema_version,
                    current_schema_version=schema_version,
                    created_by=created_by,
                )
                await self._finish_run(
                    database,
                    run_id=run_id,
                    path=path,
                    validation=validation,
                )
            except asyncio.CancelledError as error:
                await self._fail_run(database, run_id=run_id, error=error)
                raise
            except Exception as error:  # p2-approved-boundary: compensate-running-backup
                await self._fail_run(database, run_id=run_id, error=error)
                raise
        record = await self.get_backup(database, run_id)
        if record is None:
            raise BackupError("Созданная копия исчезла из журнала.")
        return record

    async def _finish_run(
        self,
        database: Database,
        *,
        run_id: int,
        path: Path,
        validation: BackupValidation,
    ) -> None:
        async with database.acquire() as connection:
            await connection.execute(
                """
                UPDATE backup_runs
                SET status = $2::VARCHAR,
                    file_name = $3::TEXT,
                    file_path = $4::TEXT,
                    size_bytes = $5::BIGINT,
                    sha256 = $6::CHAR(64),
                    schema_version = $7::TEXT,
                    expected_tables = $8::JSONB,
                    discovered_tables = $9::JSONB,
                    validation = $10::JSONB,
                    finished_at = NOW(),
                    error_message = $11::TEXT
                WHERE id = $1::BIGINT
                """,
                int(run_id),
                "valid" if validation.valid else "invalid",
                path.name,
                str(path),
                validation.size_bytes,
                validation.sha256,
                validation.schema_version,
                json.dumps(validation.expected_tables, ensure_ascii=False),
                json.dumps(validation.discovered_tables, ensure_ascii=False),
                json.dumps(self._validation_dict(validation), ensure_ascii=False),
                None if validation.valid else validation.message,
            )

    async def _fail_run(
        self,
        database: Database,
        *,
        run_id: int,
        error: Exception,
    ) -> None:
        async with database.acquire() as connection:
            await connection.execute(
                """
                UPDATE backup_runs
                SET status = 'failed',
                    finished_at = NOW(),
                    error_message = $2::TEXT,
                    validation = jsonb_build_object(
                        'valid', FALSE,
                        'message', $2::TEXT,
                        'checked_at', NOW()
                    )
                WHERE id = $1::BIGINT
                """,
                int(run_id),
                str(error)[:2000],
            )

    async def get_backup(
        self,
        database: Database,
        backup_id: int,
    ) -> BackupRecord | None:
        async with database.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT * FROM backup_runs WHERE id = $1::BIGINT",
                int(backup_id),
            )
        return self._row_to_record(row) if row else None

    async def list_history(
        self,
        database: Database,
        *,
        limit: int = 12,
    ) -> list[BackupRecord]:
        async with database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT *
                FROM backup_runs
                ORDER BY started_at DESC, id DESC
                LIMIT $1::INTEGER
                """,
                max(1, min(limit, 50)),
            )
        return [self._row_to_record(row) for row in rows]

    @staticmethod
    def _row_to_record(row: asyncpg.Record) -> BackupRecord:
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
            validation=dict(row["validation"] or {}),
        )

    async def verify_backup(
        self,
        database: Database,
        backup_id: int,
    ) -> BackupRecord:
        record = await self.get_backup(database, backup_id)
        if record is None:
            raise BackupError("Запись резервной копии не найдена.")
        if not record.file_path:
            raise BackupError("Файл этой копии уже удалён ротацией.")
        path = Path(record.file_path)
        async with database.acquire() as connection:
            current_schema = await self._schema_version(connection)
        expected = tuple(
            str(value)
            for value in (
                await self._expected_tables_for_record(database, backup_id)
            )
        )
        validation = await self._validate_dump(
            path,
            expected_tables=expected,
            schema_version=record.schema_version,
            current_schema_version=current_schema,
        )
        await self._finish_run(
            database,
            run_id=backup_id,
            path=path,
            validation=validation,
        )
        updated = await self.get_backup(database, backup_id)
        if updated is None:
            raise BackupError("Результат проверки не удалось сохранить.")
        return updated

    async def _expected_tables_for_record(
        self,
        database: Database,
        backup_id: int,
    ) -> tuple[str, ...]:
        async with database.acquire() as connection:
            value = await connection.fetchval(
                "SELECT expected_tables FROM backup_runs WHERE id = $1::BIGINT",
                int(backup_id),
            )
        return tuple(str(item) for item in (value or []))

    async def verify_latest(self, database: Database) -> BackupRecord:
        async with database.acquire() as connection:
            backup_id = await connection.fetchval(
                """
                SELECT id
                FROM backup_runs
                WHERE file_path IS NOT NULL
                  AND status <> 'running'
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """
            )
        if backup_id is None:
            raise BackupError("Проверять пока нечего: копий с файлами нет.")
        return await self.verify_backup(database, int(backup_id))

    async def get_settings(self, database: Database) -> BackupSettings:
        async with database.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT * FROM backup_settings WHERE id = 1"
            )
        if row is None:
            raise BackupError("Настройки резервного копирования не найдены.")
        return BackupSettings(
            daily_enabled=bool(row["daily_enabled"]),
            daily_hour=int(row["daily_hour"]),
            weekly_enabled=bool(row["weekly_enabled"]),
            weekly_weekday=int(row["weekly_weekday"]),
            weekly_hour=int(row["weekly_hour"]),
            retention_count=int(row["retention_count"]),
            timezone=str(row["timezone"]),
        )

    async def update_settings(
        self,
        database: Database,
        *,
        daily_enabled: bool | None = None,
        weekly_enabled: bool | None = None,
        retention_count: int | None = None,
        timezone_name: str | None = None,
        updated_by: int | None = None,
    ) -> BackupSettings:
        if timezone_name is not None:
            ZoneInfo(timezone_name)
        if retention_count is not None:
            retention_count = max(3, min(int(retention_count), 100))
        async with database.acquire() as connection:
            await connection.execute(
                """
                UPDATE backup_settings
                SET daily_enabled = COALESCE($1::BOOLEAN, daily_enabled),
                    weekly_enabled = COALESCE($2::BOOLEAN, weekly_enabled),
                    retention_count = COALESCE($3::INTEGER, retention_count),
                    timezone = COALESCE($4::TEXT, timezone),
                    updated_by = $5::BIGINT,
                    updated_at = NOW()
                WHERE id = 1
                """,
                daily_enabled,
                weekly_enabled,
                retention_count,
                timezone_name,
                updated_by,
            )
        return await self.get_settings(database)

    async def cleanup_old_backups(
        self,
        database: Database,
        *,
        retention_count: int | None = None,
    ) -> CleanupResult:
        settings = await self.get_settings(database)
        keep_count = retention_count or settings.retention_count
        async with database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT id, file_path, size_bytes
                FROM backup_runs
                WHERE file_path IS NOT NULL
                  AND status <> 'running'
                ORDER BY started_at DESC, id DESC
                """
            )
        records = [(int(row["id"]), row["file_path"]) for row in rows]
        kept, deleted = select_retained_paths(records, keep_count)
        freed = 0
        deleted_files = 0
        for row in rows:
            record_id = int(row["id"])
            if record_id not in deleted or not row["file_path"]:
                continue
            path = Path(str(row["file_path"]))
            size = path.stat().st_size if path.is_file() else int(row["size_bytes"] or 0)
            path.unlink(missing_ok=True)
            self._manifest_path(path).unlink(missing_ok=True)
            freed += size
            deleted_files += 1
            async with database.acquire() as connection:
                await connection.execute(
                    """
                    UPDATE backup_runs
                    SET file_path = NULL,
                        validation = validation || jsonb_build_object(
                            'deleted_by_rotation', TRUE,
                            'deleted_at', NOW()
                        )
                    WHERE id = $1::BIGINT
                    """,
                    record_id,
                )
        return CleanupResult(
            deleted_files=deleted_files,
            freed_bytes=freed,
            retained_files=len(kept),
        )

    async def _already_ran_daily(
        self,
        database: Database,
        *,
        local_now: datetime,
        timezone_name: str,
        backup_kind: str,
    ) -> bool:
        async with database.acquire() as connection:
            return bool(
                await connection.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM backup_runs
                        WHERE backup_kind = $1::VARCHAR
                          AND status IN ('valid', 'invalid', 'running')
                          AND timezone($2::TEXT, started_at)::DATE = $3::DATE
                    )
                    """,
                    backup_kind,
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
            and not await self._already_ran_daily(
                database,
                local_now=local_now,
                timezone_name=settings.timezone,
                backup_kind="weekly",
            )
        )
        if weekly_due:
            record = await self.create_backup(database, backup_kind="weekly")
            await self.cleanup_old_backups(database)
            return record

        daily_due = (
            settings.daily_enabled
            and local_now.hour >= settings.daily_hour
            and not await self._already_ran_daily(
                database,
                local_now=local_now,
                timezone_name=settings.timezone,
                backup_kind="daily",
            )
        )
        if daily_due:
            record = await self.create_backup(database, backup_kind="daily")
            await self.cleanup_old_backups(database)
            return record
        return None


async def run_backup_worker(
    service: BackupService,
    database: Database,
    *,
    interval_seconds: int = 300,
) -> None:
    while True:
        try:
            record = await service.run_scheduled_if_due(database)
            if record is not None:
                logger.info(
                    "Scheduled backup completed kind=%s status=%s file=%s",
                    record.backup_kind,
                    record.status,
                    record.file_name,
                )
        except asyncio.CancelledError:
            raise
        except Exception:  # p2-approved-boundary: isolate-backup-worker-iteration
            logger.exception("Scheduled backup worker failed")
        await asyncio.sleep(max(60, int(interval_seconds)))
