from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.archive import ArchivePage, ArchivedMedia, PreviewRecord
from velvet_bot.domains.characters.models import CharacterRecord
from velvet_bot.infrastructure.telegram.archive_previews import (
    TelegramArchivePreviewResolver,
    is_telegram_thumbnail_source,
)


def make_page(mime_type: str = "image/png") -> ArchivePage:
    return ArchivePage(
        character=CharacterRecord(
            id=1,
            name="Каин",
            created_by=10,
            created_in_chat=10,
            created_at=datetime(2026, 7, 16, tzinfo=UTC),
            archive_chat_id=None,
            archive_thread_id=None,
            archive_topic_url=None,
        ),
        media=ArchivedMedia(
            id=2,
            telegram_file_id="document-id",
            media_type="document",
            original_file_name="image.bin",
            storage_file_name="stored.bin",
            mime_type=mime_type,
            file_size=100,
            linked_at=datetime(2026, 7, 16, tzinfo=UTC),
        ),
        offset=0,
        total=1,
    )


class ArchivePreviewResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_stored_photo_is_reused(self) -> None:
        repository = SimpleNamespace(
            load=AsyncMock(
                return_value=PreviewRecord(
                    "photo-file-id", "unique", 800, 1200,
                    "generated_preview", None, None, None, None,
                )
            )
        )
        bot = SimpleNamespace(download=AsyncMock())
        resolver = TelegramArchivePreviewResolver(bot=bot, repository=repository)
        self.assertEqual(
            await resolver.resolve(make_page(), cache_chat_id=10),
            "photo-file-id",
        )
        bot.download.assert_not_awaited()

    async def test_non_image_document_is_skipped(self) -> None:
        repository = SimpleNamespace(load=AsyncMock())
        resolver = TelegramArchivePreviewResolver(
            bot=SimpleNamespace(), repository=repository
        )
        self.assertIsNone(
            await resolver.resolve(
                make_page("application/octet-stream"), cache_chat_id=10
            )
        )
        repository.load.assert_not_awaited()

    def test_thumbnail_source_detection(self) -> None:
        self.assertTrue(is_telegram_thumbnail_source("source_forward_thumbnail"))
        self.assertFalse(is_telegram_thumbnail_source("generated_preview"))


if __name__ == "__main__":
    unittest.main()
