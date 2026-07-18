from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.infrastructure.telegram.archive_previews as module


class FakeRepository:
    def __init__(self, record) -> None:
        self.record = record
        self.load_calls: list[dict[str, int]] = []

    async def load(self, **kwargs):
        self.load_calls.append(kwargs)
        return self.record


class ArchivePreviewFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_builder = module.build_image_document_preview
        self.builder_calls: list[tuple[object, object]] = []
        self.media = SimpleNamespace(
            id=11,
            is_image_document=True,
            file_size=1024,
            telegram_file_id='document-file',
        )
        self.page = SimpleNamespace(
            character=SimpleNamespace(id=7),
            media=self.media,
        )

    def tearDown(self) -> None:
        module.build_image_document_preview = self.original_builder

    def _resolver(self, record):
        repository = FakeRepository(record)
        resolver = module.TelegramArchivePreviewResolver(
            bot=object(),
            repository=repository,
        )
        return resolver, repository

    async def test_new_full_quality_cache_is_reused_without_rebuild(self) -> None:
        record = SimpleNamespace(
            file_id='cached-photo',
            source=module.FULL_QUALITY_PHOTO_SOURCE,
        )
        resolver, repository = self._resolver(record)

        async def unexpected_builder(bot, media):
            raise AssertionError('preview must not be rebuilt')

        module.build_image_document_preview = unexpected_builder

        result = await resolver.resolve(self.page, cache_chat_id=99)

        self.assertEqual(result, 'cached-photo')
        self.assertEqual(
            repository.load_calls,
            [{'character_id': 7, 'media_id': 11}],
        )

    async def test_legacy_cache_is_ignored_and_full_quality_preview_is_built(self) -> None:
        record = SimpleNamespace(
            file_id='legacy-thumbnail',
            source='generated_preview',
        )
        resolver, _ = self._resolver(record)
        preview = object()

        async def builder(bot, media):
            self.builder_calls.append((bot, media))
            return preview

        module.build_image_document_preview = builder

        result = await resolver.resolve(self.page, cache_chat_id=99)

        self.assertIs(result, preview)
        self.assertEqual(len(self.builder_calls), 1)
        self.assertIs(self.builder_calls[0][1], self.media)

    async def test_oversized_document_returns_none_without_download(self) -> None:
        self.media.file_size = module.DEFAULT_BOT_API_DOWNLOAD_LIMIT + 1
        record = SimpleNamespace(file_id=None, source=None)
        resolver, _ = self._resolver(record)

        async def unexpected_builder(bot, media):
            raise AssertionError('oversized media must not be downloaded')

        module.build_image_document_preview = unexpected_builder

        result = await resolver.resolve(self.page, cache_chat_id=99)

        self.assertIsNone(result)

    async def test_preview_failure_logs_and_falls_back_to_none(self) -> None:
        record = SimpleNamespace(file_id=None, source=None)
        resolver, _ = self._resolver(record)
        error = RuntimeError('preview conversion failed')

        async def fail_builder(bot, media):
            raise error

        module.build_image_document_preview = fail_builder

        with self.assertLogs(module.logger, level='INFO') as captured:
            result = await resolver.resolve(self.page, cache_chat_id=99)

        self.assertIsNone(result)
        rendered = '\n'.join(captured.output)
        self.assertIn('media_id=11', rendered)
        self.assertIn('preview conversion failed', rendered)

    async def test_preview_cancellation_is_not_swallowed(self) -> None:
        record = SimpleNamespace(file_id=None, source=None)
        resolver, _ = self._resolver(record)

        async def cancel_builder(bot, media):
            raise asyncio.CancelledError

        module.build_image_document_preview = cancel_builder

        with self.assertRaises(asyncio.CancelledError):
            await resolver.resolve(self.page, cache_chat_id=99)


if __name__ == '__main__':
    unittest.main()
