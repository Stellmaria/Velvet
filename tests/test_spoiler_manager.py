import unittest
from datetime import UTC, datetime

from velvet_bot.archive_catalog import ArchivePage, ArchivedMedia
from velvet_bot.archive_ui import build_input_media
from velvet_bot.database import Character
from velvet_bot.public_catalog import PublicMediaState
from velvet_bot.public_manager_ui import build_manager_archive_keyboard
from velvet_bot.public_ui import PublicArchiveCallback


class SpoilerManagerUiTests(unittest.TestCase):
    def setUp(self) -> None:
        character = Character(
            id=77,
            name="Кайл Блэк",
            created_by=1,
            created_in_chat=2,
            created_at=datetime(2026, 7, 16, tzinfo=UTC),
            archive_chat_id=None,
            archive_thread_id=None,
            archive_topic_url=None,
        )
        media = ArchivedMedia(
            id=15,
            telegram_file_id="photo-id",
            media_type="photo",
            original_file_name=None,
            storage_file_name="photo.jpg",
            mime_type="image/jpeg",
            file_size=100,
            linked_at=datetime(2026, 7, 16, tzinfo=UTC),
            is_spoiler=True,
        )
        self.page = ArchivePage(
            character=character,
            media=media,
            offset=0,
            total=1,
        )
        self.state = PublicMediaState(
            like_count=0,
            liked_by_user=False,
            subscribed=False,
        )

    def test_photo_input_media_keeps_spoiler(self) -> None:
        input_media = build_input_media(self.page.media, "caption")
        self.assertTrue(input_media.has_spoiler)

    def test_manager_keyboard_contains_archive_actions(self) -> None:
        keyboard = build_manager_archive_keyboard(
            self.page,
            self.state,
            category="male",
            universe="lagerta",
            story_id=2,
        )
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("📥 Скачать файлом", labels)
        self.assertIn("🔞 Убрать спойлер", labels)
        self.assertIn("🗑 Удалить", labels)
        self.assertIn("👥 Пол / состав", labels)
        self.assertIn("🎭 Вселенная", labels)
        self.assertIn("📖 История", labels)

    def test_manager_delete_callback_uses_public_prefix(self) -> None:
        keyboard = build_manager_archive_keyboard(
            self.page,
            self.state,
            category="male",
            universe="lagerta",
            story_id=2,
        )
        button = next(
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.text == "🗑 Удалить"
        )
        self.assertTrue(button.callback_data.startswith("pub:"))
        callback = PublicArchiveCallback.unpack(button.callback_data)
        self.assertEqual("pdel", callback.action)
        self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)


if __name__ == "__main__":
    unittest.main()
