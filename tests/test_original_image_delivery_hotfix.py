from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.app.original_image_delivery_hotfix import (
    _send_image_and_document_reliably,
)


class OriginalImageDeliveryHotfixTests(unittest.IsolatedAsyncioTestCase):
    async def test_original_document_is_sent_before_preview(self) -> None:
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
            send_message=AsyncMock(),
        )

        async def retry(_name, operation):
            return await operation()

        worker = SimpleNamespace(
            _bot=bot,
            _send_telegram_with_retry=retry,
        )

        await _send_image_and_document_reliably(
            worker,
            chat_id=100,
            payload=b"original-image-bytes",
            filename="result.png",
            caption="Генерация готова",
        )

        self.assertEqual(["document", "photo"], order)
        bot.send_document.assert_awaited_once()
        bot.send_photo.assert_awaited_once()
        bot.send_message.assert_not_awaited()
        self.assertIs(
            True,
            bot.send_document.await_args.kwargs[
                "disable_content_type_detection"
            ],
        )
        self.assertIn(
            "без сжатия Telegram",
            bot.send_document.await_args.kwargs["caption"],
        )
        self.assertEqual(
            "Предпросмотр изображения.",
            bot.send_photo.await_args.kwargs["caption"],
        )

    async def test_document_failure_does_not_block_preview_and_is_reported(self) -> None:
        bot = SimpleNamespace(
            send_document=AsyncMock(side_effect=RuntimeError("document upload failed")),
            send_photo=AsyncMock(),
            send_message=AsyncMock(),
        )

        async def retry(_name, operation):
            return await operation()

        worker = SimpleNamespace(
            _bot=bot,
            _send_telegram_with_retry=retry,
        )

        await _send_image_and_document_reliably(
            worker,
            chat_id=100,
            payload=b"original-image-bytes",
            filename="result.png",
            caption="Генерация готова",
        )

        bot.send_document.assert_awaited_once()
        bot.send_photo.assert_awaited_once()
        bot.send_message.assert_awaited_once()
        self.assertEqual(
            "Генерация готова",
            bot.send_photo.await_args.kwargs["caption"],
        )
        warning = bot.send_message.await_args.args[1]
        self.assertIn("Оригинальный файл: <b>не отправлен</b>", warning)
        self.assertIn("Предпросмотр: <b>отправлен</b>", warning)
        self.assertIn("Новая платная генерация не запускалась", warning)

    async def test_preview_failure_keeps_original_file_and_is_reported(self) -> None:
        bot = SimpleNamespace(
            send_document=AsyncMock(),
            send_photo=AsyncMock(side_effect=RuntimeError("preview failed")),
            send_message=AsyncMock(),
        )

        async def retry(_name, operation):
            return await operation()

        worker = SimpleNamespace(
            _bot=bot,
            _send_telegram_with_retry=retry,
        )

        await _send_image_and_document_reliably(
            worker,
            chat_id=100,
            payload=b"original-image-bytes",
            filename="result.png",
            caption="Генерация готова",
        )

        bot.send_document.assert_awaited_once()
        bot.send_photo.assert_awaited_once()
        bot.send_message.assert_awaited_once()
        warning = bot.send_message.await_args.args[1]
        self.assertIn("Оригинальный файл: <b>отправлен</b>", warning)
        self.assertIn("Предпросмотр: <b>не отправлен</b>", warning)


if __name__ == "__main__":
    unittest.main()
