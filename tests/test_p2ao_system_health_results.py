from __future__ import annotations

import unittest
from types import SimpleNamespace

import velvet_bot.services.system_health as module


class FakeRepository:
    def __init__(self) -> None:
        self.ping_error = None
        self.snapshot = SimpleNamespace(latest_backup_status='valid')
        self.ping_calls = 0
        self.snapshot_calls = 0

    async def ping(self) -> None:
        self.ping_calls += 1
        if self.ping_error is not None:
            raise self.ping_error

    async def get_runtime_snapshot(self):
        self.snapshot_calls += 1
        return self.snapshot


class FakeBot:
    def __init__(self) -> None:
        self.error = None
        self.calls = 0

    async def get_me(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return SimpleNamespace(username='velvet_bot')


class FakeWorkers:
    def snapshots(self):
        return ()


def build_service(repository):
    service = module.SystemHealthService(
        repository=repository,
        backup_dir='.',
        pg_dump_path='pg_dump',
        pg_restore_path='pg_restore',
        app_version='test',
    )
    service._disk_snapshot = lambda: module.DiskSnapshot(
        path='.', total_bytes=100, used_bytes=50, free_bytes=50
    )
    service._tool_available = lambda configured: True
    return service


class SystemHealthResultTests(unittest.IsolatedAsyncioTestCase):
    async def test_database_failure_preserves_telegram_result(self) -> None:
        repository = FakeRepository()
        repository.ping_error = RuntimeError('postgres unavailable')
        bot = FakeBot()

        report = await build_service(repository).check(
            bot=bot,
            worker_manager=FakeWorkers(),
        )

        self.assertEqual(report.status, 'failed')
        self.assertFalse(report.database_ok)
        self.assertEqual(report.database_error, 'postgres unavailable')
        self.assertIsNone(report.database)
        self.assertTrue(report.telegram_ok)
        self.assertEqual(report.bot_username, 'velvet_bot')
        self.assertEqual(repository.snapshot_calls, 0)
        self.assertEqual(bot.calls, 1)

    async def test_telegram_failure_preserves_database_result(self) -> None:
        repository = FakeRepository()
        bot = FakeBot()
        bot.error = RuntimeError('telegram unavailable')

        report = await build_service(repository).check(
            bot=bot,
            worker_manager=FakeWorkers(),
        )

        self.assertEqual(report.status, 'failed')
        self.assertTrue(report.database_ok)
        self.assertIs(report.database, repository.snapshot)
        self.assertFalse(report.telegram_ok)
        self.assertEqual(report.telegram_error, 'telegram unavailable')
        self.assertIsNone(report.bot_username)
        self.assertEqual(repository.snapshot_calls, 1)
        self.assertEqual(bot.calls, 1)


if __name__ == '__main__':
    unittest.main()
