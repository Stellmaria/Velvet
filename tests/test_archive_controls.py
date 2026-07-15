import unittest
from datetime import UTC, datetime

from velvet_bot.archive_catalog import ArchivePage, ArchivedMedia
from velvet_bot.archive_ui import (
    ArchiveMediaCallback,
    build_archive_navigation,
    build_delete_confirmation,
)
from velvet_bot.config import _parse_optional_chat_id
from velvet_bot.database import Character
from velvet_bot.handlers.archive import parse_guest_save_character


class ArchiveControlsTests(unittest.TestCase):
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
            archive_message_id=55,
        )
        self.page = ArchivePage(
            character=self.character,
            media=self.media,
            offset=0,
            total=2,
        )

    def test_image_document_is_detected_for_full_preview(self) -> None:
        self.assertTrue(self.media.is_image_document)

    def test_archive_navigation_has_delete_action(self) -> None:
        keyboard = build_archive_navigation(self.page)
        actions = [
            ArchiveMediaCallback.unpack(button.callback_data).action
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("del", actions)
        delete_button = next(
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
            and ArchiveMediaCallback.unpack(button.callback_data).action == "del"
        )
        self.assertEqual(
            11,
            ArchiveMediaCallback.unpack(delete_button.callback_data).media_id,
        )

    def test_delete_confirmation_has_confirm_and_cancel(self) -> None:
        keyboard = build_delete_confirmation(self.page)
        actions = {
            ArchiveMediaCallback.unpack(button.callback_data).action
            for button in keyboard.inline_keyboard[0]
        }
        self.assertEqual({"delok", "delno"}, actions)
        self.assertTrue(
            all(
                ArchiveMediaCallback.unpack(button.callback_data).media_id == 11
                for button in keyboard.inline_keyboard[0]
            )
        )

    def test_log_chat_id_parser_accepts_negative_chat_id(self) -> None:
        self.assertEqual(-5367533184, _parse_optional_chat_id("-5367533184"))

    def test_mention_save_parser(self) -> None:
        self.assertEqual(
            "Аид",
            parse_guest_save_character(
                "@dominusVelvetbot save Аид",
                "dominusVelvetbot",
            ),
        )

    def test_guest_mention_can_follow_character_name(self) -> None:
        self.assertEqual(
            "Аид",
            parse_guest_save_character(
                "save Аид @dominusVelvetbot",
                "dominusVelvetbot",
            ),
        )

    def test_guest_mention_can_follow_save_keyword(self) -> None:
        self.assertEqual(
            "Аид",
            parse_guest_save_character(
                "save @dominusVelvetbot Аид",
                "dominusVelvetbot",
            ),
        )

    def test_other_bot_mention_is_rejected(self) -> None:
        self.assertIsNone(
            parse_guest_save_character(
                "save Аид @another_bot",
                "dominusVelvetbot",
            )
        )


if __name__ == "__main__":
    unittest.main()
