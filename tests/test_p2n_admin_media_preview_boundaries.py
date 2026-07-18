from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.handlers.admin_media_display as module


class FakeBot:
    def __init__(self) -> None:
        self.document_calls: list[dict[str, object]] = []

    async def send_photo(self, **kwargs):
        raise AssertionError("preview photo must not be sent after preview failure")

    async def send_document(self, **kwargs):
        self.document_calls.append(kwargs)
        return "document-message"


class AdminMediaPreviewBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_preview = module.build_image_document_preview
        self.original_caption = module.format_archive_caption
        self.original_input_media = module.build_input_media
        self.original_navigation = module.build_archive_navigation
        module.format_archive_caption = lambda page: "caption"
        module.build_archive_navigation = lambda page: "keyboard"

    def tearDown(self) -> None:
        module.build_image_document_preview = self.original_preview
        module.format_archive_caption = self.original_caption
        module.build_input_media = self.original_input_media
        module.build_archive_navigation = self.original_navigation

    @staticmethod
    def _page():
        media = SimpleNamespace(
            is_image_document=True,
            is_spoiler=False,
            media_type="document",
            telegram_file_id="original-document",
        )
        return SimpleNamespace(media=media)

    async def test_edit_preview_failure_falls_back_to_original_media(self) -> None:
        fallback = object()

        async def fail_preview(bot, media):
            raise RuntimeError("preview unavailable")

        module.build_image_document_preview = fail_preview
        module.build_input_media = lambda media, caption: fallback

        result = await module.build_admin_display_media(object(), self._page())

        self.assertIs(result, fallback)

    async def test_edit_preview_cancellation_is_not_swallowed(self) -> None:
        async def cancel_preview(bot, media):
            raise asyncio.CancelledError

        module.build_image_document_preview = cancel_preview
        with self.assertRaises(asyncio.CancelledError):
            await module.build_admin_display_media(object(), self._page())

    async def test_send_preview_failure_falls_back_to_document(self) -> None:
        async def fail_preview(bot, media):
            raise RuntimeError("preview unavailable")

        module.build_image_document_preview = fail_preview
        bot = FakeBot()

        result = await module.send_admin_archive_page(
            bot=bot,
            chat_id=17,
            page=self._page(),
        )

        self.assertEqual(result, "document-message")
        self.assertEqual(len(bot.document_calls), 1)
        self.assertEqual(bot.document_calls[0]["document"], "original-document")
        self.assertEqual(bot.document_calls[0]["chat_id"], 17)

    async def test_send_preview_cancellation_is_not_swallowed(self) -> None:
        async def cancel_preview(bot, media):
            raise asyncio.CancelledError

        module.build_image_document_preview = cancel_preview
        bot = FakeBot()

        with self.assertRaises(asyncio.CancelledError):
            await module.send_admin_archive_page(
                bot=bot,
                chat_id=17,
                page=self._page(),
            )
        self.assertEqual(bot.document_calls, [])


if __name__ == "__main__":
    unittest.main()
