from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendDocument, SendPhoto

from velvet_bot.ai_quality import AIQualityItem
from velvet_bot.presentation.telegram.routers.quality_operations_controllers import quality_ai as quality_ai_module
from velvet_bot.presentation.telegram.routers.quality_operations_controllers.quality_ai_preview import _send_preview_with_fallback
import velvet_bot.presentation.telegram.routers.quality_operations_controllers.quality_ai_preview  # noqa: F401


def _item(
    *,
    media_id: int = 907,
    media_type: str = "document",
    telegram_file_id: str = "original-file-id",
    preview_file_id: str | None = "preview-file-id",
) -> AIQualityItem:
    return AIQualityItem(
        media_id=media_id,
        file_name=f"media-{media_id} · image/png",
        media_type=media_type,
        telegram_file_id=telegram_file_id,
        preview_file_id=preview_file_id,
        status="ready",
        verdict="review",
        quality_score=80,
        confidence=90,
        report={"summary_ru": "Нужна проверка."},
        decision=None,
        error_message=None,
    )


def _bad_photo(file_id: str) -> TelegramBadRequest:
    return TelegramBadRequest(
        method=SendPhoto(chat_id=1, photo=file_id),
        message="wrong file identifier/HTTP URL specified",
    )


def _bad_document(file_id: str) -> TelegramBadRequest:
    return TelegramBadRequest(
        method=SendDocument(chat_id=1, document=file_id),
        message="wrong file identifier/HTTP URL specified",
    )


class QualityAIPreviewButtonTests(unittest.TestCase):
    def test_report_keyboard_contains_explicit_preview_button(self) -> None:
        item = _item(
            media_id=77,
            media_type="photo",
            telegram_file_id="telegram-file",
            preview_file_id=None,
        )

        markup = quality_ai_module._report_keyboard(
            item,
            section="review",
            page=0,
        )
        buttons = [button for row in markup.inline_keyboard for button in row]
        preview = [button for button in buttons if button.text == "🖼 Посмотреть фото"]

        self.assertEqual(1, len(preview))
        self.assertIn("qpreview", preview[0].callback_data or "")
        self.assertIn("77", preview[0].callback_data or "")


class QualityAIPreviewFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_preview_falls_back_to_original_document(self) -> None:
        bot = SimpleNamespace(
            send_photo=AsyncMock(side_effect=_bad_photo("preview-file-id")),
            send_document=AsyncMock(),
            send_message=AsyncMock(),
        )

        sent = await _send_preview_with_fallback(bot, 1, _item())

        self.assertTrue(sent)
        bot.send_photo.assert_awaited_once()
        bot.send_document.assert_awaited_once_with(
            chat_id=1,
            document="original-file-id",
            caption="Проверка качества · media #907\nmedia-907 · image/png",
            protect_content=False,
        )
        bot.send_message.assert_not_awaited()

    async def test_invalid_preview_falls_back_to_original_photo(self) -> None:
        bot = SimpleNamespace(
            send_photo=AsyncMock(
                side_effect=[_bad_photo("preview-file-id"), None]
            ),
            send_document=AsyncMock(),
            send_message=AsyncMock(),
        )

        sent = await _send_preview_with_fallback(
            bot,
            1,
            _item(media_type="photo"),
        )

        self.assertTrue(sent)
        self.assertEqual(2, bot.send_photo.await_count)
        self.assertEqual(
            ["preview-file-id", "original-file-id"],
            [entry.kwargs["photo"] for entry in bot.send_photo.await_args_list],
        )
        bot.send_document.assert_not_awaited()
        bot.send_message.assert_not_awaited()

    async def test_unavailable_preview_and_original_send_fallback_message(self) -> None:
        bot = SimpleNamespace(
            send_photo=AsyncMock(side_effect=_bad_photo("preview-file-id")),
            send_document=AsyncMock(side_effect=_bad_document("original-file-id")),
            send_message=AsyncMock(),
        )

        sent = await _send_preview_with_fallback(bot, 1, _item())

        self.assertFalse(sent)
        bot.send_message.assert_awaited_once_with(
            1,
            "Проверка качества · media #907\n"
            "media-907 · image/png\n"
            "Превью сейчас недоступно.",
        )


if __name__ == "__main__":
    unittest.main()
