from __future__ import annotations

import inspect
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.backup_runtime import BackupService


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


class BackupRuntimeBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_runtime_service_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(BackupService)

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("database.acquire()"), 2)
        self.assertIn(
            "database.acquire()",
            inspect.getsource(BackupService._expected_tables_for_record),
        )
        self.assertIn(
            "database.acquire()",
            inspect.getsource(BackupService._ran_kind_today),
        )

    async def test_expected_tables_preserves_json_decode_and_record_filter(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value='["media_files", "characters"]'))
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))
        service = BackupService(database_url="postgresql://test", backup_dir="backups")

        result = await service._expected_tables_for_record(database, 41)

        database.acquire.assert_called_once_with()
        self.assertTrue(context.entered)
        self.assertTrue(context.exited)
        sql, backup_id = connection.fetchval.await_args.args
        self.assertIn("expected_tables", sql)
        self.assertEqual(backup_id, 41)
        self.assertEqual(result, ("media_files", "characters"))

    async def test_ran_kind_today_preserves_timezone_date_and_kind_filter(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=True))
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))
        service = BackupService(database_url="postgresql://test", backup_dir="backups")
        local_now = datetime(2026, 7, 18, 10, 30, tzinfo=UTC)

        result = await service._ran_kind_today(
            database,
            local_now=local_now,
            timezone_name="Europe/Warsaw",
            backup_kinds=("daily", "weekly"),
        )

        self.assertTrue(result)
        sql, kinds, timezone_name, local_date = connection.fetchval.await_args.args
        self.assertIn("timezone($2::TEXT, started_at)::DATE", sql)
        self.assertEqual(kinds, ["daily", "weekly"])
        self.assertEqual(timezone_name, "Europe/Warsaw")
        self.assertEqual(local_date, local_now.date())


if __name__ == "__main__":
    unittest.main()
