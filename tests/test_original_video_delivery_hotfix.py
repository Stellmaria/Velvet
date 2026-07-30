from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.app.original_video_delivery_hotfix import (
    _send_video_and_document_reliably,
)
from velvet_bot.domains.media_generation import KieModelAlias


class OriginalVideoDeliveryHotfixTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_video_model_sends_document_before_preview(self) -> None:
        aliases = (
            KieModelAlias.GROK_IMAGINE_VIDEO,
            KieModelAlias.GROK_IMAGINE_VIDEO_15,
            KieModelAlias.SEEDANCE_15_PRO_VIDEO,
            KieModelAlias.WAN_26_IMAGE_TO_VIDEO,
        )

        for alias in aliases:
            with self.subTest(alias=alias):
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
                    send_message=AsyncMock(),
                )

                async def retry(_name, operation):
                    return await operation()

                worker = SimpleNamespace(
                    _bot=bot,
                    _send_telegram_with_retry=retry,
                )

                await _send_video_and_document_reliably(
                    worker,
                    chat_id=100,
                    payload=b"original-video-bytes",
                    filename=f"{alias.value}.mp4",
                    caption=f"Модель: {alias.display_name}",
                )

                self.assertEqual(["document", "video"], order)
                bot.send_document.assert_awaited_once()
                bot.send_video.assert_awaited_once()
                bot.send_message.assert_not_awaited()
                self.assertIs(
                    True,
                    bot.send_document.await_args.kwargs[
                        "disable_content_type_detection"
                    ],
                )

    async def test_document_failure_does_not_block_preview_and_is_reported(self) -> None:
        bot = SimpleNamespace(
            send_document=AsyncMock(side_effect=RuntimeError("document upload failed")),
            send_video=AsyncMock(),
            send_message=AsyncMock(),
        )

        async def retry(_name, operation):
            return await operation()

        worker = SimpleNamespace(
            _bot=bot,
            _send_telegram_with_retry=retry,
        )

        await _send_video_and_document_reliably(
            worker,
            chat_id=100,
            payload=b"original-video-bytes",
            filename="grok-15.mp4",
            caption="Grok Imagine Video 1.5",
        )

        bot.send_document.assert_awaited_once()
        bot.send_video.assert_awaited_once()
        bot.send_message.assert_awaited_once()
        warning = bot.send_message.await_args.args[1]
        self.assertIn("Оригинальный файл: <b>не отправлен</b>", warning)
        self.assertIn("Новая платная генерация не запускалась", warning)


if __name__ == "__main__":
    unittest.main()
