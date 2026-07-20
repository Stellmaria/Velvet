from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.archive_preview import _resend_document_for_thumbnail
from velvet_bot.presentation.telegram.routers.archive.save import _persist_descriptor_preview
from velvet_bot.media import MediaDescriptor


class LargeDocumentPreviewRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_resend_document_extracts_thumbnail_and_deletes_temporary_message(self) -> None:
        thumbnail = SimpleNamespace(
            file_id="thumb-file-id",
            file_unique_id="thumb-unique-id",
            width=320,
            height=480,
        )
        temporary = SimpleNamespace(
            message_id=99,
            document=SimpleNamespace(thumbnail=thumbnail),
            video=None,
            animation=None,
            photo=None,
        )
        bot = SimpleNamespace(
            send_document=AsyncMock(return_value=temporary),
            delete_message=AsyncMock(),
        )

        result = await _resend_document_for_thumbnail(
            bot,
            cache_chat_id=7221553045,
            file_id="large-document-file-id",
        )

        self.assertIs(result, thumbnail)
        bot.send_document.assert_awaited_once_with(
            chat_id=7221553045,
            document="large-document-file-id",
            disable_notification=True,
        )
        bot.delete_message.assert_awaited_once_with(
            chat_id=7221553045,
            message_id=99,
        )

    async def test_save_path_persists_source_thumbnail(self) -> None:
        descriptor = MediaDescriptor(
            telegram_file_id="large-document-file-id",
            telegram_file_unique_id="large-document-unique-id",
            original_file_name="large.png",
            storage_file_name="large__hash.png",
            media_type="document",
            mime_type="image/png",
            file_size=72 * 1024 * 1024,
            preview_file_id="thumb-file-id",
            preview_file_unique_id="thumb-unique-id",
            preview_width=320,
            preview_height=480,
            preview_source="source_thumbnail",
        )
        database = SimpleNamespace()

        with patch(
            "velvet_bot.presentation.telegram.routers.archive.save.set_media_preview",
            new=AsyncMock(),
        ) as mocked:
            await _persist_descriptor_preview(
                database,
                media_id=587,
                media=descriptor,
            )

        mocked.assert_awaited_once_with(
            database,
            media_id=587,
            file_id="thumb-file-id",
            file_unique_id="thumb-unique-id",
            width=320,
            height=480,
            source="source_thumbnail",
        )

    async def test_save_path_ignores_media_without_thumbnail(self) -> None:
        descriptor = MediaDescriptor(
            telegram_file_id="photo-file-id",
            telegram_file_unique_id="photo-unique-id",
            original_file_name=None,
            storage_file_name="photo.jpg",
            media_type="photo",
            mime_type="image/jpeg",
            file_size=1024,
        )

        with patch(
            "velvet_bot.presentation.telegram.routers.archive.save.set_media_preview",
            new=AsyncMock(),
        ) as mocked:
            await _persist_descriptor_preview(
                SimpleNamespace(),
                media_id=1,
                media=descriptor,
            )

        mocked.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
