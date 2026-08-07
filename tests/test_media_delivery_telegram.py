from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from velvet_bot.application.media_delivery import (
    DownloadedMedia,
    MediaDeliveryItem,
    MediaDeliveryJob,
    MediaDeliveryStatus,
    MediaDeliveryStepStatus,
    MediaDeliveryTerminalError,
)
from velvet_bot.application.media_tasks import task_result_urls
from velvet_bot.infrastructure.media_delivery_telegram import (
    TelegramMediaDeliveryTransport,
)


def _job(*, media_kind: str = "image", chat_id: int | None = 100) -> MediaDeliveryJob:
    return MediaDeliveryJob(
        task_id=uuid4(),
        provider="grs",
        provider_task_id="grs:paid-task",
        chat_id=chat_id,
        media_kind=media_kind,
        request={"model": "nano_banana_pro"},
        status=MediaDeliveryStatus.RESULT_RESOLVED,
        attempt_count=1,
        notification_status=MediaDeliveryStepStatus.PENDING,
        items=(
            MediaDeliveryItem(
                result_index=1,
                result_url="https://cdn.example/result.mp4"
                if media_kind == "video"
                else "https://cdn.example/result.png",
                url_status="available",
                download_status=MediaDeliveryStepStatus.PENDING,
                original_status=MediaDeliveryStepStatus.PENDING,
                preview_status=MediaDeliveryStepStatus.PENDING,
            ),
        ),
    )


def _media(*, media_kind: str = "image") -> DownloadedMedia:
    return DownloadedMedia(
        payload=b"result-bytes",
        file_name="result.mp4" if media_kind == "video" else "result.png",
        content_type="video/mp4" if media_kind == "video" else "image/png",
    )


class TelegramMediaDeliveryTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_image_original_precedes_preview_with_canonical_flags(self) -> None:
        order: list[str] = []

        async def send_document(*args, **kwargs):
            order.append("document")
            return SimpleNamespace(message_id=1)

        async def send_photo(*args, **kwargs):
            order.append("photo")
            return SimpleNamespace(message_id=2)

        bot = SimpleNamespace(
            send_document=AsyncMock(side_effect=send_document),
            send_photo=AsyncMock(side_effect=send_photo),
        )
        transport = TelegramMediaDeliveryTransport(bot, retry_attempts=1)
        job = _job()
        item = job.items[0]
        media = _media()

        await transport.send_original(job=job, item=item, media=media)
        await transport.send_preview(job=job, item=item, media=media)

        self.assertEqual(["document", "photo"], order)
        self.assertIs(
            True,
            bot.send_document.await_args.kwargs["disable_content_type_detection"],
        )
        self.assertIn(
            "Оригинальный файл без сжатия Telegram",
            bot.send_document.await_args.kwargs["caption"],
        )
        self.assertIn(
            "Предпросмотр",
            bot.send_photo.await_args.kwargs["caption"],
        )

    async def test_video_preview_uses_streaming_after_original(self) -> None:
        order: list[str] = []

        async def send_document(*args, **kwargs):
            order.append("document")
            return SimpleNamespace(message_id=1)

        async def send_video(*args, **kwargs):
            order.append("video")
            return SimpleNamespace(message_id=2)

        bot = SimpleNamespace(
            send_document=AsyncMock(side_effect=send_document),
            send_video=AsyncMock(side_effect=send_video),
        )
        transport = TelegramMediaDeliveryTransport(bot, retry_attempts=1)
        job = _job(media_kind="video")
        item = job.items[0]
        media = _media(media_kind="video")

        await transport.send_original(job=job, item=item, media=media)
        await transport.send_preview(job=job, item=item, media=media)

        self.assertEqual(["document", "video"], order)
        self.assertIs(True, bot.send_video.await_args.kwargs["supports_streaming"])

    async def test_direct_preview_uses_saved_provider_url_without_submit(self) -> None:
        bot = SimpleNamespace(send_photo=AsyncMock())
        transport = TelegramMediaDeliveryTransport(bot, retry_attempts=1)
        job = _job()
        item = job.items[0]

        await transport.send_direct_preview(job=job, item=item)

        bot.send_photo.assert_awaited_once()
        self.assertEqual(item.result_url, bot.send_photo.await_args.kwargs["photo"])
        self.assertIn(
            "по сохранённому URL провайдера",
            bot.send_photo.await_args.kwargs["caption"],
        )

    async def test_missing_chat_fails_before_transport_call(self) -> None:
        bot = SimpleNamespace(send_document=AsyncMock())
        transport = TelegramMediaDeliveryTransport(bot, retry_attempts=1)
        job = _job(chat_id=None)

        with self.assertRaises(MediaDeliveryTerminalError):
            await transport.send_original(
                job=job,
                item=job.items[0],
                media=_media(),
            )

        bot.send_document.assert_not_awaited()

    def test_saved_result_url_parser_ignores_empty_values(self) -> None:
        self.assertEqual(
            ("https://a.example/a.png",),
            task_result_urls(
                {
                    "result_urls": [
                        "https://a.example/a.png",
                        "",
                        None,
                    ]
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()
