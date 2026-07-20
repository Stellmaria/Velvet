import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import GetFile

from velvet_bot.ai_vision import VisionAnalysisError, VisionAnalysisTarget
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


class _OversizedRecoveryBot:
    def __init__(self) -> None:
        self.file_ids: list[str] = []
        self.sent_documents: list[tuple[int, str, bool]] = []
        self.deleted_messages: list[tuple[int, int]] = []

    async def download(self, file_id, *, destination, timeout, seek):
        self.file_ids.append(file_id)
        if file_id == "oversized-id":
            raise TelegramBadRequest(
                method=GetFile(file_id=file_id),
                message="file is too big",
            )
        destination.write(b"recovered-thumbnail-bytes")
        return destination

    async def send_document(self, *, chat_id, document, disable_notification):
        self.sent_documents.append((chat_id, document, disable_notification))
        thumbnail = SimpleNamespace(
            file_id="recovered-thumbnail-id",
            file_unique_id="recovered-thumbnail-unique-id",
            width=320,
            height=480,
        )
        return SimpleNamespace(
            message_id=501,
            document=SimpleNamespace(thumbnail=thumbnail),
            video=None,
            animation=None,
            photo=None,
        )

    async def delete_message(self, *, chat_id, message_id):
        self.deleted_messages.append((chat_id, message_id))


class _OversizedWithoutThumbnailBot(_OversizedRecoveryBot):
    async def send_document(self, *, chat_id, document, disable_notification):
        self.sent_documents.append((chat_id, document, disable_notification))
        return SimpleNamespace(
            message_id=502,
            document=SimpleNamespace(thumbnail=None),
            video=None,
            animation=None,
            photo=None,
        )


class ResilientMediaAIVisionServiceTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _service(bot, repository=None):
        return ResilientMediaAIVisionService(
            bot=bot,
            repository=repository or SimpleNamespace(),
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

    async def test_oversized_document_uses_and_persists_temporary_thumbnail(self) -> None:
        bot = _OversizedRecoveryBot()
        repository = SimpleNamespace(save_preview_file_id=AsyncMock())
        service = self._service(bot, repository)
        service.set_cache_chat_id(-1001234567890)
        target = VisionAnalysisTarget(
            media_id=2618,
            telegram_file_id="oversized-id",
            preview_file_id=None,
            mime_type="image/png",
        )

        result = await service._download_target(target)

        self.assertEqual(b"recovered-thumbnail-bytes", result)
        self.assertEqual(
            ["oversized-id", "recovered-thumbnail-id"],
            bot.file_ids,
        )
        self.assertEqual(
            [(-1001234567890, "oversized-id", True)],
            bot.sent_documents,
        )
        self.assertEqual([(-1001234567890, 501)], bot.deleted_messages)
        repository.save_preview_file_id.assert_awaited_once_with(
            2618,
            "recovered-thumbnail-id",
        )

    async def test_missing_oversized_thumbnail_becomes_terminal_media_specific_error(self) -> None:
        bot = _OversizedWithoutThumbnailBot()
        service = self._service(bot)
        service.set_cache_chat_id(-1001234567890)
        target = VisionAnalysisTarget(
            media_id=3366,
            telegram_file_id="oversized-id",
            preview_file_id=None,
            mime_type="image/png",
        )

        with self.assertRaises(VisionAnalysisError) as captured:
            await service._download_target(target)

        message = str(captured.exception)
        self.assertIn("file is too big", message)
        self.assertIn("media_key=m3366", message)
        self.assertIn("Повтор автоматически не требуется", message)
        self.assertEqual(["oversized-id"], bot.file_ids)
        self.assertEqual([(-1001234567890, 502)], bot.deleted_messages)


if __name__ == "__main__":
    unittest.main()
