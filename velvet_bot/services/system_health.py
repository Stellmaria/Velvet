from __future__ import annotations

import asyncio
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiogram import Bot

from velvet_bot.infrastructure.postgres.system_repository import (
    RuntimeDatabaseSnapshot,
    SystemRepository,
)
from velvet_bot.workers.manager import WorkerManager, WorkerSnapshot

_CONNECTION_URL_RE = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mariadb|redis|mongodb(?:\+srv)?)://[^\s]+",
    re.IGNORECASE,
)
_BOT_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(?:BOT_TOKEN|DATABASE_URL|PASSWORD|SECRET|API_KEY)\s*=\s*[^\s]+",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DiskSnapshot:
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int

    @property
    def free_percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return self.free_bytes * 100 / self.total_bytes


@dataclass(frozen=True, slots=True)
class SystemHealthReport:
    status: str
    checked_at: datetime
    started_at: datetime
    app_version: str
    process_id: int
    database_ok: bool
    database_error: str | None
    database: RuntimeDatabaseSnapshot | None
    telegram_ok: bool
    telegram_error: str | None
    bot_username: str | None
    disk: DiskSnapshot
    pg_dump_available: bool
    pg_restore_available: bool
    workers: tuple[WorkerSnapshot, ...]

    @property
    def uptime_seconds(self) -> int:
        return max(0, int((self.checked_at - self.started_at).total_seconds()))


class SystemHealthService:
    def __init__(
        self,
        *,
        repository: SystemRepository,
        backup_dir: str | Path,
        pg_dump_path: str,
        pg_restore_path: str,
        app_version: str,
    ) -> None:
        self.repository = repository
        self.backup_dir = Path(backup_dir).expanduser().resolve()
        self.pg_dump_path = pg_dump_path
        self.pg_restore_path = pg_restore_path
        self.app_version = app_version
        self.started_at = datetime.now(UTC)

    @staticmethod
    def _tool_available(configured: str) -> bool:
        candidate = Path(configured).expanduser()
        return candidate.is_file() or shutil.which(configured) is not None

    @staticmethod
    def redact_text(value: str | None) -> str | None:
        if value is None:
            return None
        redacted = _CONNECTION_URL_RE.sub("<redacted-connection-url>", value)
        redacted = _BOT_TOKEN_RE.sub("<redacted-bot-token>", redacted)
        redacted = _SECRET_ASSIGNMENT_RE.sub("<redacted-secret>", redacted)
        return redacted

    def _disk_snapshot(self) -> DiskSnapshot:
        candidate = self.backup_dir
        while not candidate.exists() and candidate != candidate.parent:
            candidate = candidate.parent
        usage = shutil.disk_usage(candidate)
        return DiskSnapshot(
            path=str(candidate),
            total_bytes=int(usage.total),
            used_bytes=int(usage.used),
            free_bytes=int(usage.free),
        )

    async def check(
        self,
        *,
        bot: Bot,
        worker_manager: WorkerManager,
    ) -> SystemHealthReport:
        checked_at = datetime.now(UTC)
        database_ok = True
        database_error: str | None = None
        database_snapshot: RuntimeDatabaseSnapshot | None = None
        try:
            await self.repository.ping()
            database_snapshot = await self.repository.get_runtime_snapshot()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # p2-approved-boundary: isolate-database-health-probe
            database_ok = False
            database_error = str(error)[:2000]

        telegram_ok = True
        telegram_error: str | None = None
        bot_username: str | None = None
        try:
            info = await bot.get_me()
            bot_username = info.username
        except asyncio.CancelledError:
            raise
        except Exception as error:  # p2-approved-boundary: isolate-telegram-health-probe
            telegram_ok = False
            telegram_error = str(error)[:2000]

        disk = self._disk_snapshot()
        workers = worker_manager.snapshots()
        pg_dump_available = self._tool_available(self.pg_dump_path)
        pg_restore_available = self._tool_available(self.pg_restore_path)

        hard_failure = (
            not database_ok
            or not telegram_ok
            or any(item.state == "failed" and item.consecutive_failures >= 3 for item in workers)
            or disk.free_percent < 2
        )
        degraded = (
            not hard_failure
            and (
                any(item.state == "failed" for item in workers)
                or disk.free_percent < 10
                or not pg_dump_available
                or not pg_restore_available
                or database_snapshot is None
                or database_snapshot.latest_backup_status not in {"valid", None}
            )
        )
        status = "failed" if hard_failure else "degraded" if degraded else "ok"

        return SystemHealthReport(
            status=status,
            checked_at=checked_at,
            started_at=self.started_at,
            app_version=self.app_version,
            process_id=os.getpid(),
            database_ok=database_ok,
            database_error=database_error,
            database=database_snapshot,
            telegram_ok=telegram_ok,
            telegram_error=telegram_error,
            bot_username=bot_username,
            disk=disk,
            pg_dump_available=pg_dump_available,
            pg_restore_available=pg_restore_available,
            workers=workers,
        )

    @classmethod
    def report_to_dict(cls, report: SystemHealthReport) -> dict[str, Any]:
        database = report.database
        return {
            "status": report.status,
            "checked_at": report.checked_at.isoformat(),
            "started_at": report.started_at.isoformat(),
            "uptime_seconds": report.uptime_seconds,
            "app_version": report.app_version,
            "process_id": report.process_id,
            "telegram": {
                "ok": report.telegram_ok,
                "bot_username": report.bot_username,
                "error": cls.redact_text(report.telegram_error),
            },
            "postgresql": {
                "ok": report.database_ok,
                "error": cls.redact_text(report.database_error),
                "database_name": database.database_name if database else None,
                "postgres_version": database.postgres_version if database else None,
                "database_size_bytes": database.database_size_bytes if database else None,
                "schema_version": database.schema_version if database else None,
                "migration_count": database.migration_count if database else None,
                "character_count": database.character_count if database else None,
                "media_count": database.media_count if database else None,
                "tracked_channel_count": database.tracked_channel_count if database else None,
                "tracked_discussion_count": (
                    database.tracked_discussion_count if database else None
                ),
            },
            "queues": {
                "scheduled_publications": (
                    database.scheduled_publications if database else None
                ),
                "publishing_publications": (
                    database.publishing_publications if database else None
                ),
                "publication_errors": database.publication_errors if database else None,
                "pending_visual_scans": (
                    database.pending_visual_scans if database else None
                ),
                "unknown_file_checks": database.unknown_file_checks if database else None,
            },
            "backup": {
                "pg_dump_available": report.pg_dump_available,
                "pg_restore_available": report.pg_restore_available,
                "latest_status": database.latest_backup_status if database else None,
                "latest_at": (
                    database.latest_backup_at.isoformat()
                    if database and database.latest_backup_at
                    else None
                ),
                "latest_file_name": (
                    database.latest_backup_file_name if database else None
                ),
            },
            "disk": {
                "path": report.disk.path,
                "total_bytes": report.disk.total_bytes,
                "used_bytes": report.disk.used_bytes,
                "free_bytes": report.disk.free_bytes,
                "free_percent": round(report.disk.free_percent, 2),
            },
            "workers": [
                {
                    "name": item.name,
                    "description": item.description,
                    "state": item.state,
                    "interval_seconds": item.interval_seconds,
                    "started_at": item.started_at.isoformat() if item.started_at else None,
                    "last_started_at": (
                        item.last_started_at.isoformat() if item.last_started_at else None
                    ),
                    "last_success_at": (
                        item.last_success_at.isoformat() if item.last_success_at else None
                    ),
                    "last_error_at": (
                        item.last_error_at.isoformat() if item.last_error_at else None
                    ),
                    "next_run_at": item.next_run_at.isoformat() if item.next_run_at else None,
                    "successful_runs": item.successful_runs,
                    "failed_runs": item.failed_runs,
                    "consecutive_failures": item.consecutive_failures,
                    "last_error": cls.redact_text(item.last_error),
                }
                for item in report.workers
            ],
        }
