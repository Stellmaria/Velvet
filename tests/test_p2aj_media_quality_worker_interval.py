from __future__ import annotations

import asyncio
import unittest

import velvet_bot.media_quality as module


class FakeRepository:
    def __init__(self, database) -> None:
        self.database = database


class FakeService:
    calls = 0

    def __init__(self, *, bot, repository) -> None:
        self.bot = bot
        self.repository = repository

    async def process_once(self) -> None:
        type(self).calls += 1
        if type(self).calls == 1:
            raise RuntimeError('first iteration failed')
        raise asyncio.CancelledError


class MediaQualityWorkerIntervalTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_interval_runs_between_failed_and_next_iteration(self) -> None:
        original_repository = module.MediaQualityRepository
        original_service = module.MediaQualityService
        original_sleep = module.asyncio.sleep
        sleeps: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        FakeService.calls = 0
        module.MediaQualityRepository = FakeRepository
        module.MediaQualityService = FakeService
        module.asyncio.sleep = fake_sleep
        try:
            with self.assertLogs(module.logger, level='ERROR'):
                with self.assertRaises(asyncio.CancelledError):
                    await module.run_media_quality_worker(
                        object(),
                        object(),
                        interval_seconds=2.5,
                    )
        finally:
            module.MediaQualityRepository = original_repository
            module.MediaQualityService = original_service
            module.asyncio.sleep = original_sleep

        self.assertEqual(FakeService.calls, 2)
        self.assertEqual(sleeps, [2.5])


if __name__ == '__main__':
    unittest.main()
