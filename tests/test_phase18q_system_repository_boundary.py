from __future__ import annotations

import inspect
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.repositories.system_repository import SystemRepository


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


class SystemRepositoryBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(SystemRepository)

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self.database.acquire()"), 2)

    async def test_ping_uses_public_acquire(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=1))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = SystemRepository(database)

        await repository.ping()

        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        connection.fetchval.assert_awaited_once_with("SELECT 1")

    async def test_runtime_snapshot_preserves_query_and_mapping(self) -> None:
        latest_backup_at = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
        row = {
            "database_name": "velvet",
            "postgres_version": "16.9",
            "database_size_bytes": 1024,
            "schema_version": "020",
            "migration_count": 20,
            "character_count": 12,
            "media_count": 90,
            "tracked_channel_count": 1,
            "tracked_discussion_count": 1,
            "scheduled_publications": 3,
            "publishing_publications": 1,
            "publication_errors": 2,
            "pending_visual_scans": 4,
            "unknown_file_checks": 5,
            "latest_backup_status": "success",
            "latest_backup_at": latest_backup_at,
            "latest_backup_file_name": "velvet.dump",
        }
        connection = SimpleNamespace(fetchrow=AsyncMock(return_value=row))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = SystemRepository(database)

        result = await repository.get_runtime_snapshot()

        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        connection.fetchrow.assert_awaited_once()
        sql = connection.fetchrow.await_args.args[0]
        self.assertIn("current_database() AS database_name", sql)
        self.assertIn("FROM publication_drafts", sql)
        self.assertIn("FROM backup_runs", sql)
        self.assertEqual(result.database_name, "velvet")
        self.assertEqual(result.postgres_version, "16.9")
        self.assertEqual(result.database_size_bytes, 1024)
        self.assertEqual(result.schema_version, "020")
        self.assertEqual(result.migration_count, 20)
        self.assertEqual(result.character_count, 12)
        self.assertEqual(result.media_count, 90)
        self.assertEqual(result.scheduled_publications, 3)
        self.assertEqual(result.publication_errors, 2)
        self.assertEqual(result.pending_visual_scans, 4)
        self.assertEqual(result.latest_backup_at, latest_backup_at)
        self.assertEqual(result.latest_backup_file_name, "velvet.dump")

    async def test_runtime_snapshot_rejects_missing_row(self) -> None:
        connection = SimpleNamespace(fetchrow=AsyncMock(return_value=None))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = SystemRepository(database)

        with self.assertRaisesRegex(RuntimeError, "системную сводку"):
            await repository.get_runtime_snapshot()


if __name__ == "__main__":
    unittest.main()
