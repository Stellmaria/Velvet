from __future__ import annotations

import asyncio
import tempfile
import unittest
from types import SimpleNamespace

from velvet_bot.services.system_health import SystemHealthService
from velvet_bot.workers.manager import PeriodicWorkerSpec, WorkerManager


class _HealthyRepository:
    async def ping(self) -> None:
        return None

    async def get_runtime_snapshot(self):
        return None


class _FailingRepository(_HealthyRepository):
    async def ping(self) -> None:
        raise RuntimeError("database unavailable")


class _CancelledRepository(_HealthyRepository):
    async def ping(self) -> None:
        raise asyncio.CancelledError


class _HealthyBot:
    async def get_me(self):
        return SimpleNamespace(username="velvet_test_bot")


class _FailingBot:
    async def get_me(self):
        raise RuntimeError("telegram unavailable")


class _CancelledBot:
    async def get_me(self):
        raise asyncio.CancelledError


class SystemHealthBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def _service(self, repository) -> SystemHealthService:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        return SystemHealthService(
            repository=repository,
            backup_dir=self.tempdir.name,
            pg_dump_path="missing-pg-dump-for-test",
            pg_restore_path="missing-pg-restore-for-test",
            app_version="test",
        )

    async def test_database_probe_failure_is_isolated_in_report(self) -> None:
        report = await self._service(_FailingRepository()).check(
            bot=_HealthyBot(),
            worker_manager=WorkerManager(),
        )

        self.assertEqual("failed", report.status)
        self.assertFalse(report.database_ok)
        self.assertEqual("database unavailable", report.database_error)
        self.assertTrue(report.telegram_ok)
        self.assertEqual("velvet_test_bot", report.bot_username)

    async def test_telegram_probe_failure_is_isolated_in_report(self) -> None:
        report = await self._service(_HealthyRepository()).check(
            bot=_FailingBot(),
            worker_manager=WorkerManager(),
        )

        self.assertEqual("failed", report.status)
        self.assertTrue(report.database_ok)
        self.assertFalse(report.telegram_ok)
        self.assertEqual("telegram unavailable", report.telegram_error)

    async def test_database_probe_cancellation_propagates(self) -> None:
        with self.assertRaises(asyncio.CancelledError):
            await self._service(_CancelledRepository()).check(
                bot=_HealthyBot(),
                worker_manager=WorkerManager(),
            )

    async def test_telegram_probe_cancellation_propagates(self) -> None:
        with self.assertRaises(asyncio.CancelledError):
            await self._service(_HealthyRepository()).check(
                bot=_CancelledBot(),
                worker_manager=WorkerManager(),
            )


class WorkerManagerBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_iteration_failure_updates_snapshot(self) -> None:
        async def fail() -> None:
            raise RuntimeError("iteration failed")

        manager = WorkerManager()
        spec = PeriodicWorkerSpec(
            name="test-worker",
            description="test",
            interval_seconds=5,
            runner=fail,
        )
        manager.register(spec)

        with self.assertLogs("velvet_bot.workers.manager", level="ERROR"):
            result = await manager._execute_once(spec)

        self.assertFalse(result)
        snapshot = manager.snapshot(spec.name)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual("failed", snapshot.state)
        self.assertEqual(1, snapshot.failed_runs)
        self.assertEqual(1, snapshot.consecutive_failures)
        self.assertEqual("iteration failed", snapshot.last_error)
        self.assertIsNotNone(snapshot.next_run_at)

    async def test_worker_iteration_cancellation_propagates(self) -> None:
        async def cancel() -> None:
            raise asyncio.CancelledError

        manager = WorkerManager()
        spec = PeriodicWorkerSpec(
            name="cancel-worker",
            description="test",
            interval_seconds=5,
            runner=cancel,
        )
        manager.register(spec)

        with self.assertRaises(asyncio.CancelledError):
            await manager._execute_once(spec)

    async def test_worker_loop_failure_is_recorded_and_stops_loop(self) -> None:
        async def noop() -> None:
            return None

        manager = WorkerManager()
        spec = PeriodicWorkerSpec(
            name="loop-worker",
            description="test",
            interval_seconds=5,
            runner=noop,
        )
        manager.register(spec)

        async def fail_once(_spec) -> bool:
            raise RuntimeError("loop infrastructure failed")

        manager._execute_once = fail_once  # type: ignore[method-assign]
        with self.assertLogs("velvet_bot.workers.manager", level="ERROR"):
            await manager._run_periodic(spec)

        snapshot = manager.snapshot(spec.name)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual("failed", snapshot.state)
        self.assertEqual(1, snapshot.failed_runs)
        self.assertEqual(1, snapshot.consecutive_failures)
        self.assertEqual(
            "Worker loop stopped: loop infrastructure failed",
            snapshot.last_error,
        )
        self.assertIsNone(snapshot.next_run_at)

    async def test_worker_loop_cancellation_propagates(self) -> None:
        async def noop() -> None:
            return None

        manager = WorkerManager()
        spec = PeriodicWorkerSpec(
            name="cancel-loop-worker",
            description="test",
            interval_seconds=5,
            runner=noop,
        )
        manager.register(spec)

        async def cancel_once(_spec) -> bool:
            raise asyncio.CancelledError

        manager._execute_once = cancel_once  # type: ignore[method-assign]
        with self.assertRaises(asyncio.CancelledError):
            await manager._run_periodic(spec)


if __name__ == "__main__":
    unittest.main()
