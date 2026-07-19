from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import InputMediaDocument, InputMediaPhoto

from velvet_bot.domains.archive.models import ArchivePage, ArchivedMedia
from velvet_bot.domains.characters.models import CharacterRecord
from velvet_bot.handlers.admin_large_media_preview import (
    _build_display_media,
    _open_image_document_as_file,
    _send_page,
)
from velvet_bot.image_preview import BOT_API_DOWNLOAD_MAX_BYTES


def _page(*, file_size: int) -> ArchivePage:
    now = datetime.now(timezone.utc)
    return ArchivePage(
        character=CharacterRecord(
            id=17,
            name="Каэль",
            created_by=1,
            created_in_chat=2,
            created_at=now,
            archive_chat_id=None,
            archive_thread_id=None,
            archive_topic_url=None,
        ),
        media=ArchivedMedia(
            id=33,
            telegram_file_id="large-image-document-file-id",
            media_type="document",
            original_file_name="large-image.png",
            storage_file_name="large-image__hash.png",
            mime_type="image/png",
            file_size=file_size,
            linked_at=now,
        ),
        offset=0,
        total=1,
    )


class AdminLargeArchiveFileOpenTests(unittest.IsolatedAsyncioTestCase):
    def test_only_image_documents_above_cloud_download_limit_use_file_mode(self) -> None:
        self.assertTrue(
            _open_image_document_as_file(
                _page(file_size=BOT_API_DOWNLOAD_MAX_BYTES + 1)
            )
        )
        self.assertFalse(
            _open_image_document_as_file(
                _page(file_size=BOT_API_DOWNLOAD_MAX_BYTES)
            )
        )

    async def test_initial_open_sends_large_image_document_without_downloading_preview(self) -> None:
        sent = SimpleNamespace(message_id=101)
        bot = SimpleNamespace(
            send_document=AsyncMock(return_value=sent),
            send_photo=AsyncMock(),
            send_video=AsyncMock(),
            send_animation=AsyncMock(),
        )
        page = _page(file_size=72 * 1024 * 1024)

        with patch(
            "velvet_bot.handlers.admin_large_media_preview.resolve_archive_image_preview",
            new=AsyncMock(),
        ) as resolver:
            result = await _send_page(
                bot=bot,
                database=SimpleNamespace(),
                chat_id=7221553045,
                page=page,
            )

        self.assertIs(result, sent)
        resolver.assert_not_awaited()
        bot.send_photo.assert_not_awaited()
        bot.send_document.assert_awaited_once()
        kwargs = bot.send_document.await_args.kwargs
        self.assertEqual(kwargs["chat_id"], 7221553045)
        self.assertEqual(kwargs["document"], "large-image-document-file-id")
        self.assertTrue(kwargs["protect_content"])

    async def test_navigation_builds_document_media_for_large_image(self) -> None:
        page = _page(file_size=72 * 1024 * 1024)

        with patch(
            "velvet_bot.handlers.admin_large_media_preview.resolve_archive_image_preview",
            new=AsyncMock(),
        ) as resolver:
            result = await _build_display_media(
                SimpleNamespace(),
                SimpleNamespace(),
                page,
                cache_chat_id=7221553045,
            )

        resolver.assert_not_awaited()
        self.assertIsInstance(result, InputMediaDocument)
        self.assertEqual(result.media, "large-image-document-file-id")

    async def test_small_image_document_still_uses_full_quality_photo_preview(self) -> None:
        page = _page(file_size=5 * 1024 * 1024)

        with patch(
            "velvet_bot.handlers.admin_large_media_preview.resolve_archive_image_preview",
            new=AsyncMock(return_value="full-quality-preview-file-id"),
        ) as resolver:
            result = await _build_display_media(
                SimpleNamespace(),
                SimpleNamespace(),
                page,
                cache_chat_id=7221553045,
            )

        resolver.assert_awaited_once()
        self.assertIsInstance(result, InputMediaPhoto)
        self.assertEqual(result.media, "full-quality-preview-file-id")


if __name__ == "__main__":
    unittest.main()
