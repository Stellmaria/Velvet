from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import BufferedInputFile

from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KiePricing,
    KieTaskRecord,
    KieTaskState,
)
from velvet_bot.domains.media_generation.file_delivery_worker import (
    KieGenerationWorker,
    _result_filename,
)


class KieOriginalFileDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def _worker(self, bot) -> KieGenerationWorker:
        return KieGenerationWorker(
            bot=bot,
            queue=SimpleNamespace(),
            client=SimpleNamespace(user_agent="Velvet-Test/1.0"),
            executor=SimpleNamespace(),
            pricing=KiePricing(),
            usd_to_rub=Decimal("100"),
        )

    async def test_image_result_is_sent_as_preview_and_original_document(self) -> None:
        bot = SimpleNamespace(
            send_photo=AsyncMock(),
            send_document=AsyncMock(),
            send_video=AsyncMock(),
            send_message=AsyncMock(),
        )
        worker = self._worker(bot)
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="4K",
        )
        record = KieTaskRecord(
            task_id="provider-123",
            state=KieTaskState.SUCCESS,
            result_urls=("https://cdn.example/generated-image",),
        )
        downloaded = SimpleNamespace(
            payload=b"original-png-bytes",
            mime_type="image/png",
        )

        with patch.object(
            worker,
            "_download_result",
            AsyncMock(return_value=downloaded),
        ):
            await worker._deliver_best_effort(
                chat_id=100,
                request=request,
                record=record,
            )

        bot.send_photo.assert_awaited_once()
        bot.send_document.assert_awaited_once()
        bot.send_video.assert_not_awaited()

        photo_call = bot.send_photo.await_args
        photo = photo_call.kwargs["photo"]
        self.assertIsInstance(photo, BufferedInputFile)
        self.assertEqual(b"original-png-bytes", photo.data)
        self.assertEqual("meow-provider-123-1.png", photo.filename)
        self.assertIn("предпросмотр и оригинальный файл", photo_call.kwargs["caption"])

        document_call = bot.send_document.await_args
        document = document_call.kwargs["document"]
        self.assertIsInstance(document, BufferedInputFile)
        self.assertEqual(b"original-png-bytes", document.data)
        self.assertEqual("meow-provider-123-1.png", document.filename)
        self.assertEqual(
            "Оригинальный файл изображения.",
            document_call.kwargs["caption"],
        )

    async def test_video_result_is_sent_as_preview_and_original_document(self) -> None:
        bot = SimpleNamespace(
            send_photo=AsyncMock(),
            send_document=AsyncMock(),
            send_video=AsyncMock(),
            send_message=AsyncMock(),
        )
        worker = self._worker(bot)
        request = KieGenerationRequest(
            model=KieModelAlias.GROK_IMAGINE_VIDEO,
            input_mode=KieInputMode.TEXT,
            prompt="slow camera movement",
            resolution="720p",
            duration_seconds=6,
        )
        record = KieTaskRecord(
            task_id="video-1",
            state=KieTaskState.SUCCESS,
            result_urls=("https://cdn.example/result.mp4",),
        )
        downloaded = SimpleNamespace(
            payload=b"original-mp4-bytes",
            mime_type="video/mp4",
        )

        with patch.object(
            worker,
            "_download_result",
            AsyncMock(return_value=downloaded),
        ):
            await worker._deliver_best_effort(
                chat_id=100,
                request=request,
                record=record,
            )

        bot.send_video.assert_awaited_once()
        bot.send_document.assert_awaited_once()
        bot.send_photo.assert_not_awaited()

        video_call = bot.send_video.await_args
        self.assertEqual(100, video_call.args[0])
        video = video_call.kwargs["video"]
        self.assertIsInstance(video, BufferedInputFile)
        self.assertEqual(b"original-mp4-bytes", video.data)
        self.assertEqual("meow-video-1-1.mp4", video.filename)
        self.assertIs(True, video_call.kwargs["supports_streaming"])

        document_call = bot.send_document.await_args
        document = document_call.kwargs["document"]
        self.assertIsInstance(document, BufferedInputFile)
        self.assertEqual(b"original-mp4-bytes", document.data)
        self.assertEqual("meow-video-1-1.mp4", document.filename)
        self.assertEqual("Оригинальный видеофайл.", document_call.kwargs["caption"])

    async def test_rejected_image_preview_still_sends_original_document(self) -> None:
        from aiogram.exceptions import TelegramBadRequest
        from aiogram.methods import SendPhoto

        bot = SimpleNamespace(
            send_photo=AsyncMock(
                side_effect=TelegramBadRequest(
                    method=SendPhoto(chat_id=100, photo="file-id"),
                    message="photo invalid dimensions",
                )
            ),
            send_document=AsyncMock(),
            send_video=AsyncMock(),
            send_message=AsyncMock(),
        )
        worker = self._worker(bot)

        await worker._send_image_and_document(
            chat_id=100,
            payload=b"image",
            filename="result.png",
            caption="Готово",
        )

        bot.send_document.assert_awaited_once()
        call = bot.send_document.await_args
        self.assertEqual("Готово\n\nОригинальный файл изображения.", call.kwargs["caption"])

    async def test_rejected_video_preview_still_sends_original_document(self) -> None:
        from aiogram.exceptions import TelegramBadRequest
        from aiogram.methods import SendVideo

        bot = SimpleNamespace(
            send_photo=AsyncMock(),
            send_document=AsyncMock(),
            send_video=AsyncMock(
                side_effect=TelegramBadRequest(
                    method=SendVideo(chat_id=100, video="file-id"),
                    message="wrong file identifier/HTTP URL specified",
                )
            ),
            send_message=AsyncMock(),
        )
        worker = self._worker(bot)

        await worker._send_video_and_document(
            chat_id=100,
            payload=b"video",
            filename="result.mp4",
            caption="Готово",
        )

        bot.send_document.assert_awaited_once()
        call = bot.send_document.await_args
        document = call.kwargs["document"]
        self.assertIsInstance(document, BufferedInputFile)
        self.assertEqual(b"video", document.data)
        self.assertEqual("result.mp4", document.filename)
        self.assertEqual("Готово\n\nОригинальный видеофайл.", call.kwargs["caption"])

    def test_result_filename_uses_provider_extension_when_available(self) -> None:
        self.assertEqual(
            "meow-provider-1-2.webp",
            _result_filename(
                url="https://cdn.example/path/output.webp?token=secret",
                provider_task_id="provider-1",
                index=2,
                mime_type="application/octet-stream",
                video=False,
            ),
        )
        self.assertEqual(
            "meow-provider-1-1.mp4",
            _result_filename(
                url="https://cdn.example/path/output",
                provider_task_id="provider-1",
                index=1,
                mime_type="video/mp4",
                video=True,
            ),
        )


if __name__ == "__main__":
    unittest.main()
