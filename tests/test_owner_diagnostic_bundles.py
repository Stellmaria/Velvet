from __future__ import annotations

import json
import logging
import unittest
import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.error_center import ErrorIncident
from velvet_bot.infrastructure.postgres.system_repository import RuntimeDatabaseSnapshot
from velvet_bot.services.diagnostic_bundle import DiagnosticBundleService
from velvet_bot.services.system_health import DiskSnapshot, SystemHealthReport
from velvet_bot.workers.manager import WorkerSnapshot


def _database_snapshot(*, backup_status: str = "valid") -> RuntimeDatabaseSnapshot:
    return RuntimeDatabaseSnapshot(
        database_name="velvet",
        postgres_version="16.9",
        database_size_bytes=1024,
        schema_version="020",
        migration_count=20,
        character_count=12,
        media_count=90,
        tracked_channel_count=1,
        tracked_discussion_count=1,
        scheduled_publications=0,
        publishing_publications=0,
        publication_errors=0,
        pending_visual_scans=0,
        unknown_file_checks=0,
        latest_backup_status=backup_status,
        latest_backup_at=datetime.now(UTC),
        latest_backup_file_name="velvet.dump",
    )


def _report(
    *,
    status: str = "ok",
    database_ok: bool = True,
    telegram_ok: bool = True,
    worker: WorkerSnapshot | None = None,
    backup_status: str = "valid",
) -> SystemHealthReport:
    now = datetime.now(UTC)
    return SystemHealthReport(
        status=status,
        checked_at=now,
        started_at=now - timedelta(hours=2),
        app_version="1.3.0",
        process_id=123,
        database_ok=database_ok,
        database_error=None if database_ok else "DATABASE_URL=postgresql://u:p@host/db",
        database=_database_snapshot(backup_status=backup_status) if database_ok else None,
        telegram_ok=telegram_ok,
        telegram_error=None if telegram_ok else "token 1234567890:abcdefghijklmnopqrstuvwxyzABCDE",
        bot_username="velvet_bot",
        disk=DiskSnapshot(
            path="diagnostics",
            total_bytes=1000,
            used_bytes=500,
            free_bytes=500,
        ),
        pg_dump_available=True,
        pg_restore_available=True,
        workers=(worker,) if worker else (),
    )


def _critical_incident() -> ErrorIncident:
    now = datetime.now(UTC)
    return ErrorIncident(
        id=7,
        fingerprint="a" * 64,
        severity="CRITICAL",
        logger_name="velvet_bot.test",
        summary="failed API_KEY=super-secret",
        details="DATABASE_URL=postgresql://user:password@localhost/db",
        occurrence_count=3,
        first_seen_at=now - timedelta(minutes=5),
        last_seen_at=now,
        acknowledged_at=None,
        acknowledged_by=None,
        log_chat_message_id=None,
    )


class DiagnosticBundleTests(unittest.IsolatedAsyncioTestCase):
    def test_supported_windows_are_explicit_and_bounded(self) -> None:
        self.assertEqual(1, DiagnosticBundleService.parse_window("1h"))
        self.assertEqual(24, DiagnosticBundleService.parse_window("1d"))
        self.assertEqual(72, DiagnosticBundleService.parse_window("3d"))
        self.assertEqual(168, DiagnosticBundleService.parse_window("7d"))
        with self.assertRaises(ValueError):
            DiagnosticBundleService.parse_window("30d")

    async def test_bundle_has_stable_files_and_redacts_secrets(self) -> None:
        repository = SimpleNamespace(
            unacknowledged=AsyncMock(return_value=(_critical_incident(),))
        )
        service = DiagnosticBundleService(
            incident_repository=repository,
            app_version="1.3.0",
            owner_user_ids=frozenset({10}),
        )
        record = logging.LogRecord(
            name="velvet_bot.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="BOT_TOKEN=1234567890:abcdefghijklmnopqrstuvwxyzABCDE",
            args=(),
            exc_info=None,
        )
        service._log_buffer.emit(record)

        bundle = await service.build_bundle(
            report=_report(),
            window_hours=24,
            reason="test",
        )

        with zipfile.ZipFile(BytesIO(bundle.payload)) as archive:
            self.assertEqual(
                {
                    "environment_safe.json",
                    "incidents.json",
                    "manifest.json",
                    "recent_logs.txt",
                    "runtime_snapshot.json",
                    "summary.md",
                    "workers.json",
                },
                set(archive.namelist()),
            )
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual("velvet-diagnostic-bundle/v1", manifest["schema"])
            self.assertEqual("test", manifest["reason"])
            combined = b"\n".join(archive.read(name) for name in archive.namelist()).decode(
                "utf-8"
            )
        self.assertNotIn("super-secret", combined)
        self.assertNotIn("password@localhost", combined)
        self.assertNotIn("1234567890:", combined)
        self.assertIn("<redacted-secret>", combined)

    async def test_automatic_critical_bundle_obeys_cooldown(self) -> None:
        incident = _critical_incident()
        repository = SimpleNamespace(unacknowledged=AsyncMock(return_value=(incident,)))
        service = DiagnosticBundleService(
            incident_repository=repository,
            app_version="1.3.0",
            owner_user_ids=frozenset({100}),
        )
        system_service = SimpleNamespace(check=AsyncMock(return_value=_report()))
        bot = SimpleNamespace(send_document=AsyncMock())
        worker_manager = SimpleNamespace()

        first = await service.monitor_once(
            bot=bot,
            system_service=system_service,
            worker_manager=worker_manager,
        )
        second = await service.monitor_once(
            bot=bot,
            system_service=system_service,
            worker_manager=worker_manager,
        )

        self.assertEqual(1, first)
        self.assertEqual(0, second)
        bot.send_document.assert_awaited_once()


    async def test_telegram_alert_requires_three_consecutive_failures(self) -> None:
        repository = SimpleNamespace(unacknowledged=AsyncMock(return_value=()))
        service = DiagnosticBundleService(
            incident_repository=repository,
            app_version="1.3.0",
            owner_user_ids=frozenset({100}),
        )
        system_service = SimpleNamespace(
            check=AsyncMock(
                side_effect=(
                    _report(status="failed", telegram_ok=False),
                    _report(status="failed", telegram_ok=False),
                    _report(status="failed", telegram_ok=False),
                )
            )
        )
        bot = SimpleNamespace(send_document=AsyncMock())
        worker_manager = SimpleNamespace()

        results = [
            await service.monitor_once(
                bot=bot,
                system_service=system_service,
                worker_manager=worker_manager,
            )
            for _ in range(3)
        ]

        self.assertEqual([0, 0, 1], results)
        bot.send_document.assert_awaited_once()

    async def test_successful_telegram_probe_resets_failure_streak(self) -> None:
        repository = SimpleNamespace(unacknowledged=AsyncMock(return_value=()))
        service = DiagnosticBundleService(
            incident_repository=repository,
            app_version="1.3.0",
            owner_user_ids=frozenset({100}),
        )
        system_service = SimpleNamespace(
            check=AsyncMock(
                side_effect=(
                    _report(status="failed", telegram_ok=False),
                    _report(),
                    _report(status="failed", telegram_ok=False),
                    _report(status="failed", telegram_ok=False),
                )
            )
        )
        bot = SimpleNamespace(send_document=AsyncMock())
        worker_manager = SimpleNamespace()

        results = [
            await service.monitor_once(
                bot=bot,
                system_service=system_service,
                worker_manager=worker_manager,
            )
            for _ in range(4)
        ]

        self.assertEqual([0, 0, 0, 0], results)
        bot.send_document.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
