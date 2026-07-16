from __future__ import annotations

import io
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.types import BufferedInputFile
from PIL import Image

from velvet_bot.domains.archive import ArchivePage, ArchivedMedia, PreviewRecord
from velvet_bot.domains.characters.models import CharacterRecord
from velvet_bot.infrastructure.telegram.archive_previews import (
    DEFAULT_BOT_API_DOWNLOAD_LIMIT,
    FULL_QUALITY_PHOTO_SOURCE,
    TelegramArchivePreviewResolver,
    is_telegram_thumbnail_source,
)


def make_page(
    mime_type: str = "image/png",
    *,
    file_size: int = 100,
) -> ArchivePage:
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
            original_file_name="image.png",
            storage_file_name="stored.png",
            mime_type=mime_type,
            file_size=file_size,
            linked_at=datetime(2026, 7, 16, tzinfo=UTC),
        ),
        offset=0,
        total=1,
    )


def png_bytes() -> bytes:
    output = io.BytesIO()
    image = Image.new("RGB", (800, 1200), (20, 30, 40))
    image.save(output, format="PNG")
    image.close()
    return output.getvalue()


class ArchivePreviewResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_quality_photo_is_reused(self) -> None:
        repository = SimpleNamespace(
            load=AsyncMock(
                return_value=PreviewRecord(
                    "photo-file-id",
                    "unique",
                    800,
                    1200,
                    FULL_QUALITY_PHOTO_SOURCE,
                    None,
                    None,
                    None,
                    None,
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

    async def test_old_generated_preview_is_ignored_and_rebuilt(self) -> None:
        repository = SimpleNamespace(
            load=AsyncMock(
                return_value=PreviewRecord(
                    "old-low-quality-id",
                    "unique",
                    800,
                    1200,
                    "generated_preview",
                    None,
                    None,
                    None,
                    None,
                )
            )
        )

        async def download(_file_id, *, destination, seek):
            self.assertTrue(seek)
            destination.write(png_bytes())

        bot = SimpleNamespace(download=AsyncMock(side_effect=download))
        resolver = TelegramArchivePreviewResolver(bot=bot, repository=repository)

        result = await resolver.resolve(make_page(), cache_chat_id=10)

        self.assertIsInstance(result, BufferedInputFile)
        bot.download.assert_awaited_once()

    async def test_image_above_20_mb_has_no_thumbnail_or_document_fallback(self) -> None:
        repository = SimpleNamespace(
            load=AsyncMock(return_value=PreviewRecord(None, None, None, None, None, None, None, None, None))
        )
        bot = SimpleNamespace(
            download=AsyncMock(),
            forward_message=AsyncMock(),
            send_document=AsyncMock(),
        )
        resolver = TelegramArchivePreviewResolver(bot=bot, repository=repository)

        result = await resolver.resolve(
            make_page(file_size=DEFAULT_BOT_API_DOWNLOAD_LIMIT + 1),
            cache_chat_id=10,
        )

        self.assertIsNone(result)
        bot.download.assert_not_awaited()
        bot.forward_message.assert_not_awaited()
        bot.send_document.assert_not_awaited()

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
        self.assertFalse(is_telegram_thumbnail_source(FULL_QUALITY_PHOTO_SOURCE))


if __name__ == "__main__":
    unittest.main()
