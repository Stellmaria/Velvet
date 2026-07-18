from __future__ import annotations

import asyncio
import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.media_quality.models import MediaScanTarget
from velvet_bot.domains.media_quality.service import MediaQualityService


class MediaQualityBroadBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_scan_compensation_boundary_is_explicit(self) -> None:
        source = inspect.getsource(MediaQualityService.scan_target)
        self.assertIn(
            "p2-approved-boundary: compensate-claimed-media-scan",
            source,
        )

    async def test_unexpected_scan_failure_is_recorded_for_claimed_target(self) -> None:
        error = RuntimeError("download failed")
        bot = SimpleNamespace(download=AsyncMock(side_effect=error))
        repository = SimpleNamespace(mark_scan_error=AsyncMock())
        service = MediaQualityService(bot=bot, repository=repository)
        target = MediaScanTarget(
            media_id=17,
            telegram_file_id="file-id",
            display_name="image.jpg",
        )

        await service.scan_target(target)

        repository.mark_scan_error.assert_awaited_once_with(
            media_id=17,
            error=error,
            broken_file=False,
        )

    async def test_scan_cancellation_is_not_compensated_or_suppressed(self) -> None:
        bot = SimpleNamespace(
            download=AsyncMock(side_effect=asyncio.CancelledError())
        )
        repository = SimpleNamespace(mark_scan_error=AsyncMock())
        service = MediaQualityService(bot=bot, repository=repository)
        target = MediaScanTarget(
            media_id=18,
            telegram_file_id="file-id",
            display_name="image.jpg",
        )

        with self.assertRaises(asyncio.CancelledError):
            await service.scan_target(target)

        repository.mark_scan_error.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
