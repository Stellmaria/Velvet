import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import GetFile

from velvet_bot.ai_vision import VisionAnalysisTarget
from velvet_bot.resilient_ai_vision import ResilientMediaAIVisionService


class _RetryingBot:
    def __init__(self) -> None:
        self.calls = 0
        self.timeouts: list[int] = []

    async def download(self, file_id, *, destination, timeout, seek):
        self.calls += 1
        self.timeouts.append(timeout)
        if self.calls < 3:
            raise TelegramNetworkError(
                method=GetFile(file_id=file_id),
                message="ServerDisconnectedError: Server disconnected",
            )
        destination.write(b"image-bytes")
        return destination


class _PreviewFallbackBot:
    def __init__(self) -> None:
        self.file_ids: list[str] = []

    async def download(self, file_id, *, destination, timeout, seek):
        self.file_ids.append(file_id)
        if file_id == "original-id":
            raise TelegramBadRequest(
                method=GetFile(file_id=file_id),
                message="wrong file identifier",
            )
        destination.write(b"preview-bytes")
        return destination


class ResilientMediaAIVisionServiceTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _service(bot):
        return ResilientMediaAIVisionService(
            bot=bot,
            repository=SimpleNamespace(),
            client=SimpleNamespace(),
            max_attempts=3,
        )

    async def test_transient_telegram_failure_is_retried_inside_one_attempt(self) -> None:
        bot = _RetryingBot()
        service = self._service(bot)
        target = VisionAnalysisTarget(
            media_id=78,
            telegram_file_id="original-id",
            preview_file_id=None,
            mime_type="image/jpeg",
        )

        with patch(
            "velvet_bot.resilient_ai_vision.asyncio.sleep",
            new=AsyncMock(),
        ) as sleep:
            result = await service._download_target(target)

        self.assertEqual(b"image-bytes", result)
        self.assertEqual(3, bot.calls)
        self.assertEqual([90, 90, 90], bot.timeouts)
        self.assertEqual(2, sleep.await_count)

    async def test_bad_original_file_uses_saved_preview_without_retry_loop(self) -> None:
        bot = _PreviewFallbackBot()
        service = self._service(bot)
        target = VisionAnalysisTarget(
            media_id=79,
            telegram_file_id="original-id",
            preview_file_id="preview-id",
            mime_type="image/jpeg",
        )

        result = await service._download_target(target)

        self.assertEqual(b"preview-bytes", result)
        self.assertEqual(["original-id", "preview-id"], bot.file_ids)


if __name__ == "__main__":
    unittest.main()
