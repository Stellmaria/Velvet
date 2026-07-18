from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.publication_worker as module


class FakeService:
    outcomes: list[BaseException | None] = []

    def __init__(self) -> None:
        self.calls = 0

    async def process_due_once(self) -> None:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if outcome is not None:
            raise outcome


class PublicationWorkerBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_recovers_after_failure_and_honors_interval(self) -> None:
        original_builder = module.build_publication_service
        original_asyncio = module.asyncio
        service = FakeService()
        FakeService.outcomes = [
            RuntimeError('publication batch failed'),
            asyncio.CancelledError(),
        ]
        sleeps: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        module.build_publication_service = lambda bot, database: service
        module.asyncio = SimpleNamespace(
            CancelledError=asyncio.CancelledError,
            sleep=fake_sleep,
        )
        try:
            with self.assertLogs(module.logger, level='ERROR') as captured:
                with self.assertRaises(asyncio.CancelledError):
                    await module.run_publication_worker(
                        object(),
                        object(),
                        interval_seconds=2.5,
                    )
        finally:
            module.build_publication_service = original_builder
            module.asyncio = original_asyncio

        self.assertEqual(service.calls, 2)
        self.assertEqual(sleeps, [2.5])
        rendered = '\n'.join(captured.output)
        self.assertIn('Publication queue loop failed', rendered)
        self.assertIn('publication batch failed', rendered)

    async def test_first_cancellation_is_terminal_without_error_log(self) -> None:
        original_builder = module.build_publication_service
        service = FakeService()
        FakeService.outcomes = [asyncio.CancelledError()]
        module.build_publication_service = lambda bot, database: service
        try:
            with self.assertNoLogs(module.logger, level='ERROR'):
                with self.assertRaises(asyncio.CancelledError):
                    await module.run_publication_worker(
                        object(),
                        object(),
                        interval_seconds=0,
                    )
        finally:
            module.build_publication_service = original_builder

        self.assertEqual(service.calls, 1)


if __name__ == '__main__':
    unittest.main()
