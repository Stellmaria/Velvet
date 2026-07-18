from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.public_archive_display as module


class FakeTelegramAPIError(Exception):
    pass


class FakeInputMediaPhoto:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class FakeBot:
    def __init__(self) -> None:
        self.photo_calls: list[dict[str, object]] = []
        self.document_calls: list[dict[str, object]] = []
        self.photo_error: BaseException | None = None

    async def send_photo(self, **kwargs):
        self.photo_calls.append(kwargs)
        if self.photo_error is not None:
            raise self.photo_error
        return 'photo-message'

    async def send_document(self, **kwargs):
        self.document_calls.append(kwargs)
        return 'document-message'


class PublicArchiveDisplayFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_builder = module.build_image_document_preview
        self.original_build_input = module.build_input_media
        self.original_input_photo = module.InputMediaPhoto
        self.original_api_error = module.TelegramAPIError
        self.original_load_state = module.load_public_state
        self.original_keyboard = module.build_viewer_keyboard
        self.original_caption = module.format_public_archive_caption

        module.InputMediaPhoto = FakeInputMediaPhoto
        module.TelegramAPIError = FakeTelegramAPIError
        module.format_public_archive_caption = lambda page, state: 'viewer caption'

        async def load_state(database, page, user_id):
            return SimpleNamespace(user_id=user_id)

        async def keyboard(*args, **kwargs):
            return 'viewer keyboard'

        module.load_public_state = load_state
        module.build_viewer_keyboard = keyboard

        self.media = SimpleNamespace(
            id=11,
            media_type='document',
            telegram_file_id='original-document',
            is_image_document=True,
            is_spoiler=True,
        )
        self.page = SimpleNamespace(
            character=SimpleNamespace(id=7, name='Ada'),
            media=self.media,
        )

    def tearDown(self) -> None:
        module.build_image_document_preview = self.original_builder
        module.build_input_media = self.original_build_input
        module.InputMediaPhoto = self.original_input_photo
        module.TelegramAPIError = self.original_api_error
        module.load_public_state = self.original_load_state
        module.build_viewer_keyboard = self.original_keyboard
        module.format_public_archive_caption = self.original_caption

    async def test_edit_preview_failure_falls_back_to_original_input_media(self) -> None:
        fallback = object()
        calls: list[tuple[object, str]] = []

        async def fail_preview(bot, media):
            raise RuntimeError('preview failed')

        def build_input(media, caption):
            calls.append((media, caption))
            return fallback

        module.build_image_document_preview = fail_preview
        module.build_input_media = build_input

        with self.assertLogs(module.logger, level='ERROR'):
            result = await module.build_viewer_input_media(
                object(),
                self.page,
                object(),
            )

        self.assertIs(result, fallback)
        self.assertEqual(calls, [(self.media, 'viewer caption')])

    async def test_edit_preview_cancellation_is_not_swallowed(self) -> None:
        async def cancel_preview(bot, media):
            raise asyncio.CancelledError

        module.build_image_document_preview = cancel_preview
        module.build_input_media = lambda media, caption: self.fail(
            'fallback must not run after cancellation'
        )

        with self.assertRaises(asyncio.CancelledError):
            await module.build_viewer_input_media(object(), self.page, object())

    async def test_edit_preview_success_preserves_caption_parse_mode_and_spoiler(self) -> None:
        preview = object()

        async def build_preview(bot, media):
            return preview

        module.build_image_document_preview = build_preview

        result = await module.build_viewer_input_media(
            object(),
            self.page,
            object(),
        )

        self.assertIsInstance(result, FakeInputMediaPhoto)
        self.assertIs(result.kwargs['media'], preview)
        self.assertEqual(result.kwargs['caption'], 'viewer caption')
        self.assertEqual(result.kwargs['parse_mode'], module.ParseMode.HTML)
        self.assertTrue(result.kwargs['has_spoiler'])

    async def test_send_preview_generation_failure_falls_back_to_document(self) -> None:
        async def fail_preview(bot, media):
            raise RuntimeError('conversion failed')

        module.build_image_document_preview = fail_preview
        bot = FakeBot()

        with self.assertLogs(module.logger, level='ERROR'):
            result = await module.send_viewer_archive_page(
                bot=bot,
                database=object(),
                chat_id=23,
                page=self.page,
                viewer_user_id=17,
            )

        self.assertEqual(result, 'document-message')
        self.assertEqual(bot.photo_calls, [])
        self.assertEqual(len(bot.document_calls), 1)
        call = bot.document_calls[0]
        self.assertEqual(call['document'], 'original-document')
        self.assertEqual(call['chat_id'], 23)
        self.assertEqual(call['caption'], 'viewer caption')
        self.assertEqual(call['reply_markup'], 'viewer keyboard')

    async def test_send_photo_telegram_failure_falls_back_to_document(self) -> None:
        async def build_preview(bot, media):
            return 'compressed-photo'

        module.build_image_document_preview = build_preview
        bot = FakeBot()
        bot.photo_error = FakeTelegramAPIError('photo rejected')

        with self.assertLogs(module.logger, level='INFO'):
            result = await module.send_viewer_archive_page(
                bot=bot,
                database=object(),
                chat_id=23,
                page=self.page,
                viewer_user_id=17,
            )

        self.assertEqual(result, 'document-message')
        self.assertEqual(len(bot.photo_calls), 1)
        self.assertEqual(bot.photo_calls[0]['photo'], 'compressed-photo')
        self.assertTrue(bot.photo_calls[0]['has_spoiler'])
        self.assertEqual(len(bot.document_calls), 1)
        self.assertEqual(bot.document_calls[0]['document'], 'original-document')

    async def test_send_preview_cancellation_is_not_swallowed(self) -> None:
        async def cancel_preview(bot, media):
            raise asyncio.CancelledError

        module.build_image_document_preview = cancel_preview
        bot = FakeBot()

        with self.assertRaises(asyncio.CancelledError):
            await module.send_viewer_archive_page(
                bot=bot,
                database=object(),
                chat_id=23,
                page=self.page,
                viewer_user_id=17,
            )

        self.assertEqual(bot.photo_calls, [])
        self.assertEqual(bot.document_calls, [])


if __name__ == '__main__':
    unittest.main()
