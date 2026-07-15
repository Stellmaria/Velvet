import unittest
from datetime import UTC, datetime

from velvet_bot.archive_catalog import ArchivePage, ArchivedMedia
from velvet_bot.character_directory import CategorySummary
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
    build_public_category_menu,
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

    def test_category_menu_opens_selected_category(self) -> None:
        keyboard = build_public_category_menu(
            [CategorySummary("male", "Мужской", "👨", 3)]
        )
        callback = PublicArchiveCallback.unpack(
            keyboard.inline_keyboard[0][0].callback_data
        )
        self.assertEqual("menu", callback.action)
        self.assertEqual("male", callback.category)

    def test_character_menu_opens_archive_by_button(self) -> None:
        menu_page = PublicCharacterPage(
            items=[
                PublicCharacterItem(
                    character=self.character,
                    category="male",
                    prompt_post_url=None,
                    media_count=3,
                )
            ],
            category="male",
            page=0,
            page_size=6,
            total_characters=1,
        )
        keyboard = build_public_character_menu(menu_page)
        callback = PublicArchiveCallback.unpack(
            keyboard.inline_keyboard[0][0].callback_data
        )
        self.assertEqual("open", callback.action)
        self.assertEqual(self.character.id, callback.character_id)
        self.assertEqual("male", callback.category)

    def test_prompt_button_appears_only_when_url_exists(self) -> None:
        without_prompt = PublicCharacterPage(
            items=[PublicCharacterItem(self.character, "male", None, 3)],
            category="male",
            page=0,
            page_size=6,
            total_characters=1,
        )
        with_prompt = PublicCharacterPage(
            items=[
                PublicCharacterItem(
                    self.character,
                    "male",
                    "https://t.me/velvet/123",
                    3,
                )
            ],
            category="male",
            page=0,
            page_size=6,
            total_characters=1,
        )
        labels_without = [
            button.text
            for row in build_public_character_menu(without_prompt).inline_keyboard
            for button in row
        ]
        labels_with = [
            button.text
            for row in build_public_character_menu(with_prompt).inline_keyboard
            for button in row
        ]
        self.assertNotIn("📝 Промт", labels_without)
        self.assertIn("📝 Промт", labels_with)

    def test_public_keyboard_has_like_and_subscription(self) -> None:
        keyboard = build_public_archive_keyboard(
            self.page,
            self.state,
            viewer_user_id=100,
            category="male",
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
