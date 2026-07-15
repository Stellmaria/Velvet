import unittest
from datetime import UTC, datetime

from aiogram.types import InputMediaDocument, InputMediaPhoto

from velvet_bot.archive_catalog import ArchivePage, ArchivedMedia
from velvet_bot.archive_ui import (
    ArchiveMediaCallback,
    build_archive_navigation,
    build_input_media,
    format_archive_caption,
)
from velvet_bot.database import Character


class ArchiveBrowserUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.character = Character(
            id=7,
            name="Аид",
            created_by=1,
            created_in_chat=2,
            created_at=datetime(2026, 7, 15, tzinfo=UTC),
            archive_chat_id=-1003951213065,
            archive_thread_id=1398,
            archive_topic_url="https://t.me/c/3951213065/1398",
        )
        self.media = ArchivedMedia(
            id=11,
            telegram_file_id="file-id",
            media_type="document",
            original_file_name="result.png",
            storage_file_name="result__hash.png",
            mime_type="image/png",
            file_size=123,
            linked_at=datetime(2026, 7, 15, 18, 0, tzinfo=UTC),
        )

    def test_callback_payload_fits_telegram_limit(self) -> None:
        payload = ArchiveMediaCallback(
            action="show",
            character_id=7,
            offset=999999,
        ).pack()
        self.assertLessEqual(len(payload.encode("utf-8")), 64)

    def test_navigation_wraps_around_archive(self) -> None:
        page = ArchivePage(
            character=self.character,
            media=self.media,
            offset=0,
            total=3,
        )
        keyboard = build_archive_navigation(page)
        previous = ArchiveMediaCallback.unpack(
            keyboard.inline_keyboard[0][0].callback_data
        )
        following = ArchiveMediaCallback.unpack(
            keyboard.inline_keyboard[0][2].callback_data
        )
        self.assertEqual(2, previous.offset)
        self.assertEqual(1, following.offset)

    def test_single_item_has_no_redundant_arrows(self) -> None:
        page = ArchivePage(
            character=self.character,
            media=self.media,
            offset=0,
            total=1,
        )
        keyboard = build_archive_navigation(page)
        self.assertEqual(1, len(keyboard.inline_keyboard[0]))
        self.assertEqual("1 / 1", keyboard.inline_keyboard[0][0].text)

    def test_document_stays_document_in_browser(self) -> None:
        result = build_input_media(self.media, "caption")
        self.assertIsInstance(result, InputMediaDocument)

    def test_photo_stays_photo_in_browser(self) -> None:
        photo = ArchivedMedia(
            id=self.media.id,
            telegram_file_id=self.media.telegram_file_id,
            media_type="photo",
            original_file_name=None,
            storage_file_name="photo__hash.jpg",
            mime_type="image/jpeg",
            file_size=self.media.file_size,
            linked_at=self.media.linked_at,
        )
        result = build_input_media(photo, "caption")
        self.assertIsInstance(result, InputMediaPhoto)

    def test_caption_contains_character_and_position(self) -> None:
        page = ArchivePage(
            character=self.character,
            media=self.media,
            offset=1,
            total=4,
        )
        caption = format_archive_caption(page)
        self.assertIn("Аид", caption)
        self.assertIn("2</b> из <b>4", caption)
        self.assertIn("result.png", caption)


if __name__ == "__main__":
    unittest.main()
