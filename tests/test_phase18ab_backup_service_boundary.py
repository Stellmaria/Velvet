from __future__ import annotations

import inspect
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from velvet_bot.backup_service import (
    BackupService,
    BackupSettings,
    BackupValidation,
)


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        self.exited = True
        return False


class BackupServiceBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_service_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(BackupService)

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("database.acquire()"), 15)

    async def test_insert_running_run_preserves_status_and_returned_id(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=41))
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))
        service = BackupService(database_url="postgresql://test", backup_dir="backups")

        result = await service._insert_running_run(
            database,
            backup_kind="manual",
            created_by=99,
        )

        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        sql, backup_kind, created_by = connection.fetchval.await_args.args
        self.assertIn("VALUES ($1::VARCHAR, 'running'", sql)
        self.assertEqual(backup_kind, "manual")
        self.assertEqual(created_by, 99)
        self.assertEqual(result, 41)

    async def test_finish_run_preserves_validation_payload_and_status(self) -> None:
        connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))
        service = BackupService(database_url="postgresql://test", backup_dir="backups")
        validation = BackupValidation(
            valid=True,
            readable=True,
            size_bytes=1234,
            sha256="a" * 64,
            expected_tables=("characters", "media_files"),
            discovered_tables=("characters", "media_files"),
            missing_tables=(),
            schema_version="010.sql",
            current_schema_version="010.sql",
            schema_matches=True,
            message="Архив корректен.",
        )
        path = Path("backups/velvet.dump")

        await service._finish_run(
            database,
            run_id=51,
            path=path,
            validation=validation,
        )

        arguments = connection.execute.await_args.args
        self.assertIn("UPDATE backup_runs", arguments[0])
        self.assertEqual(arguments[1], 51)
        self.assertEqual(arguments[2], "valid")
        self.assertEqual(arguments[3], "velvet.dump")
        self.assertEqual(arguments[4], str(path))
        self.assertEqual(arguments[5], 1234)
        self.assertEqual(arguments[6], "a" * 64)
        self.assertEqual(json.loads(arguments[8]), ["characters", "media_files"])
        self.assertTrue(json.loads(arguments[10])["valid"])
        self.assertIsNone(arguments[11])

    async def test_update_settings_preserves_clamp_and_returns_current_settings(self) -> None:
        connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))
        service = BackupService(database_url="postgresql://test", backup_dir="backups")
        expected = BackupSettings(
            daily_enabled=True,
            daily_hour=3,
            weekly_enabled=False,
            weekly_weekday=6,
            weekly_hour=4,
            retention_count=100,
            timezone="Europe/Warsaw",
        )

        with patch.object(
            service,
            "get_settings",
            new=AsyncMock(return_value=expected),
        ) as get_settings:
            result = await service.update_settings(
                database,
                daily_enabled=True,
                weekly_enabled=False,
                retention_count=999,
                timezone_name="Europe/Warsaw",
                updated_by=77,
            )

        arguments = connection.execute.await_args.args
        self.assertIn("UPDATE backup_settings", arguments[0])
        self.assertEqual(arguments[1:], (True, False, 100, "Europe/Warsaw", 77))
        get_settings.assert_awaited_once_with(database)
        self.assertEqual(result, expected)

    async def test_already_ran_daily_preserves_timezone_and_local_date(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=True))
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))
        service = BackupService(database_url="postgresql://test", backup_dir="backups")
        local_now = datetime(2026, 7, 18, 9, 15, tzinfo=UTC)

        result = await service._already_ran_daily(
            database,
            local_now=local_now,
            timezone_name="Europe/Warsaw",
            backup_kind="daily",
        )

        self.assertTrue(result)
        sql, kind, timezone_name, local_date = connection.fetchval.await_args.args
        self.assertIn("timezone($2::TEXT, started_at)::DATE", sql)
        self.assertEqual(kind, "daily")
        self.assertEqual(timezone_name, "Europe/Warsaw")
        self.assertEqual(local_date, local_now.date())


if __name__ == "__main__":
    unittest.main()
