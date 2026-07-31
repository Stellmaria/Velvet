from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.domains.media_generation.economy_worker import (
    KieGenerationWorker as EconomyKieGenerationWorker,
)
from velvet_bot.domains.media_generation.friendly_worker import (
    FriendlyKieGenerationWorker,
)


class MediaResultAutoDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_generation_runs_delivery_recovery_immediately(self) -> None:
        worker = object.__new__(FriendlyKieGenerationWorker)
        recover_once = AsyncMock(side_effect=(0, 1))
        worker._media_delivery_runtime = SimpleNamespace(recover_once=recover_once)

        with patch.object(
            EconomyKieGenerationWorker,
            "process_once",
            new=AsyncMock(return_value=1),
        ):
            processed = await worker.process_once()

        self.assertEqual(1, processed)
        self.assertEqual(2, recover_once.await_count)

    async def test_idle_iteration_does_not_duplicate_recovery_pass(self) -> None:
        worker = object.__new__(FriendlyKieGenerationWorker)
        recover_once = AsyncMock(return_value=0)
        worker._media_delivery_runtime = SimpleNamespace(recover_once=recover_once)

        with patch.object(
            EconomyKieGenerationWorker,
            "process_once",
            new=AsyncMock(return_value=0),
        ):
            processed = await worker.process_once()

        self.assertEqual(0, processed)
        recover_once.assert_awaited_once_with()

    async def test_delivery_recovery_error_does_not_requeue_paid_generation(self) -> None:
        worker = object.__new__(FriendlyKieGenerationWorker)
        recover_once = AsyncMock(side_effect=RuntimeError("delivery database unavailable"))
        worker._media_delivery_runtime = SimpleNamespace(recover_once=recover_once)
        provider_process = AsyncMock(return_value=1)

        with patch.object(
            EconomyKieGenerationWorker,
            "process_once",
            new=provider_process,
        ):
            processed = await worker.process_once()

        self.assertEqual(1, processed)
        provider_process.assert_awaited_once_with()
        self.assertEqual(2, recover_once.await_count)


if __name__ == "__main__":
    unittest.main()
