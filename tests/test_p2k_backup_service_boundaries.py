from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import velvet_bot.backup_service as backup


class Acquire:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class Database:
    def acquire(self) -> Acquire:
        return Acquire()


class BackupServiceBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def _service(self, directory: Path, failure: BaseException):
        service = backup.BackupService(
            database_url="postgresql://example",
            backup_dir=directory,
        )
        failed: list[tuple[int, BaseException]] = []

        async def insert_run(database, **kwargs) -> int:
            return 9

        async def schema(connection):
            return None

        async def tables(connection):
            return ()

        async def create_dump(**kwargs):
            raise failure

        async def fail_run(database, *, run_id: int, error: BaseException) -> None:
            failed.append((run_id, error))

        service._insert_running_run = insert_run
        service._schema_version = schema
        service._public_tables = tables
        service._create_dump_file = create_dump
        service._fail_run = fail_run
        return service, failed

    async def test_failure_marks_running_backup_failed_and_reraises(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            error = RuntimeError("dump failed")
            service, failed = self._service(Path(value), error)
            with self.assertRaises(RuntimeError):
                await service.create_backup(Database(), backup_kind="manual")
            self.assertEqual(failed, [(9, error)])

    async def test_cancellation_marks_running_backup_failed_and_reraises(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            error = asyncio.CancelledError()
            service, failed = self._service(Path(value), error)
            with self.assertRaises(asyncio.CancelledError):
                await service.create_backup(Database(), backup_kind="manual")
            self.assertEqual(failed, [(9, error)])

    async def test_worker_isolates_iteration_failure_but_propagates_stop(self) -> None:
        class Service:
            calls = 0

            async def run_scheduled_if_due(self, database):
                self.calls += 1
                raise RuntimeError("iteration failed")

        service = Service()
        original_sleep = backup.asyncio.sleep

        async def stop(delay: float) -> None:
            raise asyncio.CancelledError

        backup.asyncio.sleep = stop
        try:
            with self.assertRaises(asyncio.CancelledError):
                await backup.run_backup_worker(service, Database(), interval_seconds=60)
        finally:
            backup.asyncio.sleep = original_sleep
        self.assertEqual(service.calls, 1)


if __name__ == "__main__":
    unittest.main()
