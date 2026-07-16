from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest

from velvet_bot.domains.media_quality import (
    MediaFileCheckTarget,
    MediaQualityService,
    MediaScanTarget,
)


class MediaQualityServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_once_coordinates_scan_and_file_check_queues(self) -> None:
        scan_target = MediaScanTarget(1, "scan-file", "one.png")
        check_target = MediaFileCheckTarget(2, "check-file")
        repository = SimpleNamespace(
            claim_pending_images=AsyncMock(return_value=[scan_target]),
            claim_file_checks=AsyncMock(return_value=[check_target]),
            load_other_fingerprints=AsyncMock(return_value=[]),
            store_fingerprint_and_candidates=AsyncMock(),
            mark_scan_error=AsyncMock(),
            record_file_check=AsyncMock(),
        )
        bot = SimpleNamespace(
            download=AsyncMock(),
            get_file=AsyncMock(),
        )
        service = MediaQualityService(bot=bot, repository=repository)
        service.scan_target = AsyncMock()  # type: ignore[method-assign]
        service.verify_file = AsyncMock()  # type: ignore[method-assign]

        result = await service.process_once()

        self.assertEqual(result.fingerprint_targets, 1)
        self.assertEqual(result.file_checks, 1)
        service.scan_target.assert_awaited_once_with(scan_target)
        service.verify_file.assert_awaited_once_with(
            media_id=2,
            telegram_file_id="check-file",
        )

    async def test_oversized_media_is_not_marked_as_broken(self) -> None:
        repository = SimpleNamespace(
            load_other_fingerprints=AsyncMock(return_value=[]),
            store_fingerprint_and_candidates=AsyncMock(),
            mark_scan_error=AsyncMock(),
        )
        bot = SimpleNamespace(
            download=AsyncMock(
                side_effect=TelegramBadRequest(
                    method=None,
                    message="file is too big",
                )
            )
        )
        service = MediaQualityService(bot=bot, repository=repository)
        target = MediaScanTarget(587, "large-file-id", "large.png")

        await service.scan_target(target)

        repository.mark_scan_error.assert_awaited_once()
        call = repository.mark_scan_error.await_args
        self.assertEqual(call.kwargs["media_id"], 587)
        self.assertFalse(call.kwargs["broken_file"])
        repository.store_fingerprint_and_candidates.assert_not_awaited()

    async def test_file_check_records_telegram_failure(self) -> None:
        repository = SimpleNamespace(record_file_check=AsyncMock())
        bot = SimpleNamespace(
            get_file=AsyncMock(
                side_effect=TelegramBadRequest(
                    method=None,
                    message="wrong file identifier",
                )
            )
        )
        service = MediaQualityService(bot=bot, repository=repository)

        await service.verify_file(media_id=9, telegram_file_id="broken")

        repository.record_file_check.assert_awaited_once()
        call = repository.record_file_check.await_args
        self.assertEqual(call.kwargs["status"], "broken")
        self.assertIn("wrong file identifier", call.kwargs["error_text"])


if __name__ == "__main__":
    unittest.main()
