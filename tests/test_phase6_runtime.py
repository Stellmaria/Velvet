import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from velvet_bot.database import Database
from velvet_bot.presentation.telegram.routers.system import SystemCallback, _format_bytes
from velvet_bot.repositories.system_repository import (
    RuntimeDatabaseSnapshot,
    SystemRepository,
)
from velvet_bot.services.system_health import DiskSnapshot, SystemHealthService
from velvet_bot.workers import PeriodicWorkerSpec, WorkerManager


class WorkerManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_recovers_after_failed_iteration(self) -> None:
        calls = 0

        async def runner() -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("first iteration failed")

        manager = WorkerManager()
        manager.register(
            PeriodicWorkerSpec(
                name="test-worker",
                description="Test worker",
                interval_seconds=0.01,
                runner=runner,
            )
        )
        await manager.start_all()
        try:
            for _ in range(100):
                snapshot = manager.snapshot("test-worker")
                if snapshot and snapshot.successful_runs >= 1:
                    break
                await asyncio.sleep(0.01)
            snapshot = manager.snapshot("test-worker")
            self.assertIsNotNone(snapshot)
            self.assertEqual(1, snapshot.failed_runs)
            self.assertGreaterEqual(snapshot.successful_runs, 1)
            self.assertEqual(0, snapshot.consecutive_failures)
            self.assertEqual("running", snapshot.state)
            self.assertIsNone(snapshot.last_error)
        finally:
            await manager.stop_all()
        self.assertEqual("stopped", manager.snapshot("test-worker").state)

    async def test_manual_run_and_restart_are_safe(self) -> None:
        calls = 0

        async def runner() -> None:
            nonlocal calls
            calls += 1

        manager = WorkerManager()
        manager.register(
            PeriodicWorkerSpec(
                name="manual-worker",
                description="Manual worker",
                interval_seconds=60,
                runner=runner,
                run_immediately=False,
            )
        )
        await manager.start_all()
        try:
            self.assertTrue(await manager.run_now("manual-worker"))
            self.assertEqual(1, calls)
            self.assertEqual(1, manager.snapshot("manual-worker").successful_runs)

            await manager.restart("manual-worker")
            snapshot = manager.snapshot("manual-worker")
            self.assertEqual("starting", snapshot.state)
            self.assertEqual(1, snapshot.successful_runs)
        finally:
            await manager.stop_all()

    async def test_duplicate_worker_name_is_rejected(self) -> None:
        async def runner() -> None:
            return None

        manager = WorkerManager()
        spec = PeriodicWorkerSpec("same", "Same", 1, runner)
        manager.register(spec)
        with self.assertRaises(ValueError):
            manager.register(spec)


class _RepositoryStub:
    async def ping(self) -> None:
        return None

    async def get_runtime_snapshot(self) -> RuntimeDatabaseSnapshot:
        return RuntimeDatabaseSnapshot(
            database_name="velvet",
            postgres_version="16.4",
            database_size_bytes=1024,
            schema_version="023_discussion_insights_and_backups.sql",
            migration_count=23,
            character_count=12,
            media_count=48,
            tracked_channel_count=1,
            tracked_discussion_count=1,
            scheduled_publications=2,
            publishing_publications=0,
            publication_errors=1,
            pending_visual_scans=3,
            unknown_file_checks=4,
            latest_backup_status="valid",
            latest_backup_at=datetime.now(UTC),
            latest_backup_file_name="velvet.dump",
        )


class _BotStub:
    async def get_me(self):
        return SimpleNamespace(username="dominusVelvetbot")


class SystemHealthServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_report_combines_database_disk_tools_and_workers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = WorkerManager()
            service = SystemHealthService(
                repository=_RepositoryStub(),
                backup_dir=directory,
                pg_dump_path=sys.executable,
                pg_restore_path=sys.executable,
                app_version="1.1.0-test",
            )
            with patch.object(
                service,
                "_disk_snapshot",
                return_value=DiskSnapshot(
                    path=directory,
                    total_bytes=1000,
                    used_bytes=100,
                    free_bytes=900,
                ),
            ):
                report = await service.check(bot=_BotStub(), worker_manager=manager)
            payload = service.report_to_dict(report)

        self.assertEqual("ok", report.status)
        self.assertTrue(report.database_ok)
        self.assertTrue(report.telegram_ok)
        self.assertEqual("dominusVelvetbot", report.bot_username)
        self.assertEqual("1.1.0-test", report.app_version)
        self.assertTrue(report.pg_dump_available)
        self.assertTrue(report.pg_restore_available)
        self.assertEqual("velvet", report.database.database_name)
        self.assertGreater(report.disk.total_bytes, 0)
        self.assertEqual("velvet", payload["postgresql"]["database_name"])
        self.assertEqual("valid", payload["backup"]["latest_status"])
        self.assertIn("checked_at", payload)
        json.dumps(payload)

    def test_callback_data_and_size_formatter(self) -> None:
        actions = (
            "overview",
            "workers",
            "database",
            "queues",
            "backups",
            "version",
            "export",
            "worker.public-archive-notifications",
            "run.publication-queue",
            "restart.postgresql-backups",
        )
        for action in actions:
            self.assertLessEqual(len(SystemCallback(action=action).pack().encode()), 64)
        self.assertEqual("1.0 КБ", _format_bytes(1024))


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class SystemRepositoryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_snapshot_uses_current_schema(self) -> None:
        database = Database(os.environ["TEST_DATABASE_URL"])
        await database.initialize()
        try:
            snapshot = await SystemRepository(database).get_runtime_snapshot()
        finally:
            await database.close()

        self.assertTrue(snapshot.database_name)
        self.assertTrue(snapshot.postgres_version)
        self.assertGreater(snapshot.migration_count, 0)
        self.assertTrue((snapshot.schema_version or "").endswith(".sql"))
        self.assertGreaterEqual(snapshot.database_size_bytes, 0)


if __name__ == "__main__":
    unittest.main()
