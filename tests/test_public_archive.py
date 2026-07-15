import unittest
from datetime import UTC, datetime

from velvet_bot.archive_catalog import ArchivePage, ArchivedMedia
from velvet_bot.database import Character
from velvet_bot.public_catalog import (
    PublicCharacterItem,
    PublicCharacterPage,
    PublicMediaState,
)
from velvet_bot.public_ui import (
    PUBLIC_DOWNLOAD_USER_ID,
    PublicArchiveCallback,
    build_public_archive_keyboard,
    build_public_character_menu,
)


class PublicArchiveUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.character = Character(
            id=7,
            name="Аид",
            created_by=1,
            created_in_chat=2,
            created_at=datetime(2026, 7, 15, tzinfo=UTC),
            archive_chat_id=None,
            archive_thread_id=None,
            archive_topic_url=None,
        )
        self.media = ArchivedMedia(
            id=11,
            telegram_file_id="photo-file-id",
            media_type="photo",
            original_file_name=None,
            storage_file_name="photo.jpg",
            mime_type="image/jpeg",
            file_size=100,
            linked_at=datetime(2026, 7, 15, tzinfo=UTC),
        )
        self.page = ArchivePage(
            character=self.character,
            media=self.media,
            offset=0,
            total=3,
        )
        self.state = PublicMediaState(
            like_count=4,
            liked_by_user=False,
            subscribed=False,
        )

    def test_character_menu_opens_archive_by_button(self) -> None:
        menu_page = PublicCharacterPage(
            items=[PublicCharacterItem(self.character, 3)],
            page=0,
            page_size=8,
            total_characters=1,
        )
        keyboard = build_public_character_menu(menu_page)
        callback = PublicArchiveCallback.unpack(
            keyboard.inline_keyboard[0][0].callback_data
        )
        self.assertEqual("open", callback.action)
        self.assertEqual(self.character.id, callback.character_id)

    def test_public_keyboard_has_like_and_subscription(self) -> None:
        keyboard = build_public_archive_keyboard(
            self.page,
            self.state,
            viewer_user_id=100,
        )
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("🤍 4", labels)
        self.assertIn("🔔 Подписаться", labels)
        self.assertNotIn("🗑 Удалить", labels)

    def test_download_button_is_hidden_from_regular_subscriber(self) -> None:
        keyboard = build_public_archive_keyboard(
            self.page,
            self.state,
            viewer_user_id=100,
        )
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertNotIn("📥 Скачать файлом", labels)

    def test_download_button_is_visible_only_for_allowed_id(self) -> None:
        keyboard = build_public_archive_keyboard(
            self.page,
            self.state,
            viewer_user_id=PUBLIC_DOWNLOAD_USER_ID,
        )
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("📥 Скачать файлом", labels)


if __name__ == "__main__":
    unittest.main()
