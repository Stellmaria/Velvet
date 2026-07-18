from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.ai_quality import AIQualityService
from velvet_bot.ai_vision import MediaAIVisionService
from velvet_bot.calibrated_ai_quality import CalibratedAIQualityService


class _FailingClient:
    provider = "ollama"
    model = "qwen"

    async def analyze(self, source: bytes):
        raise RuntimeError("analysis failed")


class _CancelledClient(_FailingClient):
    async def analyze(self, source: bytes):
        raise asyncio.CancelledError


def _target():
    return SimpleNamespace(
        media_id=17,
        telegram_file_id="file",
        preview_file_id=None,
        mime_type="image/jpeg",
    )


def _service(service_type, *, client):
    service = object.__new__(service_type)
    service._client = client
    service._repository = SimpleNamespace(
        claim_targets=AsyncMock(return_value=[_target()]),
        mark_ready=AsyncMock(),
        mark_error=AsyncMock(),
    )
    service._max_attempts = 3
    service._healthy = True
    service._provider_available = AsyncMock(return_value=True)
    service._download_target = AsyncMock(return_value=b"image")
    if service_type is CalibratedAIQualityService:
        service._calibration_repository = SimpleNamespace(
            profile=AsyncMock(return_value=SimpleNamespace())
        )
    return service


class AIWorkerBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_unexpected_failure_marks_claimed_target_error(self) -> None:
        for service_type in (
            AIQualityService,
            MediaAIVisionService,
            CalibratedAIQualityService,
        ):
            with self.subTest(service=service_type.__name__):
                service = _service(service_type, client=_FailingClient())
                processed = await service.process_once()

                self.assertEqual(processed, 0)
                service._repository.mark_error.assert_awaited_once()
                args = service._repository.mark_error.await_args.args
                self.assertEqual(args[0], 17)
                self.assertIsInstance(args[1], RuntimeError)

    async def test_cancellation_is_not_converted_to_item_error(self) -> None:
        for service_type in (
            AIQualityService,
            MediaAIVisionService,
            CalibratedAIQualityService,
        ):
            with self.subTest(service=service_type.__name__):
                service = _service(service_type, client=_CancelledClient())
                with self.assertRaises(asyncio.CancelledError):
                    await service.process_once()

                service._repository.mark_error.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
