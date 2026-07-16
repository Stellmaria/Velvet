from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from aiogram import Bot

from velvet_bot.repositories.system_repository import (
    RuntimeDatabaseSnapshot,
    SystemRepository,
)
from velvet_bot.workers.manager import WorkerManager, WorkerSnapshot


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
        except Exception as error:
            database_ok = False
            database_error = str(error)[:2000]

        telegram_ok = True
        telegram_error: str | None = None
        bot_username: str | None = None
        try:
            info = await bot.get_me()
            bot_username = info.username
        except Exception as error:
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
