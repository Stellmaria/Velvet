from __future__ import annotations

import unittest
from types import SimpleNamespace

import velvet_bot.public_archive_display as module


class PublicArchiveDisplayNonImageTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_image_document_bypasses_preview_builder(self) -> None:
        original_builder = module.build_image_document_preview
        original_input = module.build_input_media
        media = SimpleNamespace(is_image_document=False)
        page = SimpleNamespace(media=media)
        fallback = object()
        calls: list[tuple[object, str]] = []

        async def unexpected_builder(bot, item):
            raise AssertionError('preview builder must not run')

        def build_input(item, caption):
            calls.append((item, caption))
            return fallback

        module.build_image_document_preview = unexpected_builder
        module.build_input_media = build_input
        original_caption = module.format_public_archive_caption
        module.format_public_archive_caption = lambda page, state: 'caption'
        try:
            result = await module.build_viewer_input_media(
                object(),
                page,
                object(),
            )
        finally:
            module.build_image_document_preview = original_builder
            module.build_input_media = original_input
            module.format_public_archive_caption = original_caption

        self.assertIs(result, fallback)
        self.assertEqual(calls, [(media, 'caption')])


if __name__ == '__main__':
    unittest.main()
