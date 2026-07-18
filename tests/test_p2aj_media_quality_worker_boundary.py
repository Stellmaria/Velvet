from __future__ import annotations

import asyncio
import unittest

import velvet_bot.media_quality as module


class FakeRepository:
    instances: list['FakeRepository'] = []

    def __init__(self, database) -> None:
        self.database = database
        self.instances.append(self)


class FakeService:
    outcomes: list[BaseException | None] = []
    instances: list['FakeService'] = []

    def __init__(self, *, bot, repository) -> None:
        self.bot = bot
        self.repository = repository
        self.calls = 0
        self.instances.append(self)

    async def process_once(self) -> None:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if outcome is not None:
            raise outcome


class MediaQualityWorkerBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_repository = module.MediaQualityRepository
        self.original_service = module.MediaQualityService
        FakeRepository.instances = []
        FakeService.instances = []
        FakeService.outcomes = []
        module.MediaQualityRepository = FakeRepository
        module.MediaQualityService = FakeService

    def tearDown(self) -> None:
        module.MediaQualityRepository = self.original_repository
        module.MediaQualityService = self.original_service

    async def test_iteration_failure_is_logged_and_next_cycle_runs(self) -> None:
        first_error = RuntimeError('scan iteration failed')
        FakeService.outcomes = [first_error, asyncio.CancelledError()]
        bot = object()
        database = object()

        with self.assertLogs(module.logger, level='ERROR') as captured:
            with self.assertRaises(asyncio.CancelledError):
                await module.run_media_quality_worker(
                    bot,
                    database,
                    interval_seconds=0,
                )

        self.assertEqual(len(FakeService.instances), 1)
        service = FakeService.instances[0]
        self.assertEqual(service.calls, 2)
        self.assertIs(service.bot, bot)
        self.assertEqual(len(FakeRepository.instances), 1)
        self.assertIs(FakeRepository.instances[0].database, database)
        self.assertIs(service.repository, FakeRepository.instances[0])
        rendered = '\n'.join(captured.output)
        self.assertIn('Media quality worker failed', rendered)
        self.assertIn('scan iteration failed', rendered)

    async def test_first_cycle_cancellation_propagates_without_error_log(self) -> None:
        FakeService.outcomes = [asyncio.CancelledError()]

        with self.assertNoLogs(module.logger, level='ERROR'):
            with self.assertRaises(asyncio.CancelledError):
                await module.run_media_quality_worker(
                    object(),
                    object(),
                    interval_seconds=0,
                )

        self.assertEqual(FakeService.instances[0].calls, 1)


if __name__ == '__main__':
    unittest.main()
