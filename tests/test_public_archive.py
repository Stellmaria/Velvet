import unittest
from dataclasses import replace
from datetime import UTC, datetime

from velvet_bot.archive_catalog import ArchivePage, ArchivedMedia
from velvet_bot.character_directory import CategorySummary, UniverseSummary
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
    build_public_story_menu,
    build_public_universe_menu,
    format_public_archive_caption,
)
from velvet_bot.story_catalog import StorySummary


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

    def test_category_menu_opens_universe_filter(self) -> None:
        keyboard = build_public_category_menu(
            [CategorySummary("male", "Мужской", "👨", 3)]
        )
        callback = PublicArchiveCallback.unpack(
            keyboard.inline_keyboard[0][0].callback_data
        )
        self.assertEqual("universes", callback.action)
        self.assertEqual("male", callback.category)

    def test_visual_novel_universe_opens_story_filter(self) -> None:
        keyboard = build_public_universe_menu(
            "male",
            [UniverseSummary("kr", "КР", "💎", 2)],
        )
        callback = PublicArchiveCallback.unpack(
            keyboard.inline_keyboard[0][0].callback_data
        )
        self.assertEqual("stories", callback.action)
        self.assertEqual("male", callback.category)
        self.assertEqual("kr", callback.universe)

    def test_non_novel_universe_opens_characters_directly(self) -> None:
        keyboard = build_public_universe_menu(
            "male",
            [UniverseSummary("bg3", "BG3", "🎲", 2)],
        )
        callback = PublicArchiveCallback.unpack(
            keyboard.inline_keyboard[0][0].callback_data
        )
        self.assertEqual("menu", callback.action)
        self.assertEqual("bg3", callback.universe)

    def test_story_menu_uses_initials_and_keeps_filters(self) -> None:
        keyboard = build_public_story_menu(
            "male",
            "kr",
            [StorySummary(12, "kr", "kali", "КЗТ", "Кали. Зов тьмы", 3)],
        )
        button = keyboard.inline_keyboard[0][0]
        self.assertIn("КЗТ", button.text)
        callback = PublicArchiveCallback.unpack(button.callback_data)
        self.assertEqual("menu", callback.action)
        self.assertEqual("male", callback.category)
        self.assertEqual("kr", callback.universe)
        self.assertEqual(12, callback.story_id)

    def test_character_menu_opens_archive_by_button(self) -> None:
        menu_page = PublicCharacterPage(
            items=[
                PublicCharacterItem(
                    character=self.character,
                    category="male",
                    prompt_post_url=None,
                    media_count=3,
                    universe="kr",
                    story_id=12,
                    story_short_label="КЗТ",
                    story_title="Кали. Зов тьмы",
                )
            ],
            category="male",
            page=0,
            page_size=6,
            total_characters=1,
            universe="kr",
            story_id=12,
            story_short_label="КЗТ",
            story_title="Кали. Зов тьмы",
        )
        keyboard = build_public_character_menu(menu_page)
        callback = PublicArchiveCallback.unpack(
            keyboard.inline_keyboard[0][0].callback_data
        )
        self.assertEqual("open", callback.action)
        self.assertEqual(self.character.id, callback.character_id)
        self.assertEqual("male", callback.category)
        self.assertEqual("kr", callback.universe)
        self.assertEqual(12, callback.story_id)

    def test_character_menu_does_not_show_character_level_prompt(self) -> None:
        menu_page = PublicCharacterPage(
            items=[
                PublicCharacterItem(
                    self.character,
                    "male",
                    "https://t.me/legacy/123",
                    3,
                    "kr",
                    12,
                    "КЗТ",
                    "Кали. Зов тьмы",
                )
            ],
            category="male",
            page=0,
            page_size=6,
            total_characters=1,
            universe="kr",
            story_id=12,
        )
        labels = [
            button.text
            for row in build_public_character_menu(menu_page).inline_keyboard
            for button in row
        ]
        self.assertNotIn("📝 Промт", labels)

    def test_prompt_button_appears_only_on_linked_media(self) -> None:
        without_prompt = build_public_archive_keyboard(
            self.page,
            self.state,
            viewer_user_id=100,
        )
        media_with_prompt = replace(
            self.media,
            prompt_post_url="https://t.me/velvet/123",
        )
        with_prompt = build_public_archive_keyboard(
            replace(self.page, media=media_with_prompt),
            self.state,
            viewer_user_id=100,
        )
        labels_without = [
            button.text for row in without_prompt.inline_keyboard for button in row
        ]
        labels_with = [
            button.text for row in with_prompt.inline_keyboard for button in row
        ]
        self.assertNotIn("📝 Открыть промт", labels_without)
        self.assertIn("📝 Открыть промт", labels_with)

    def test_public_keyboard_has_engagement_and_preserves_filters(self) -> None:
        keyboard = build_public_archive_keyboard(
            self.page,
            self.state,
            viewer_user_id=100,
            category="male",
            universe="kr",
            story_id=12,
        )
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("🤍 4", labels)
        self.assertIn("🔔 Подписаться", labels)
        self.assertNotIn("🗑 Удалить", labels)

        actions = {
            PublicArchiveCallback.unpack(button.callback_data).action
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertIn("like", actions)
        self.assertIn("sub", actions)
        self.assertNotIn("download", actions)

        back = next(
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.text == "↩️ К персонажам"
        )
        callback = PublicArchiveCallback.unpack(back.callback_data)
        self.assertEqual("male", callback.category)
        self.assertEqual("kr", callback.universe)
        self.assertEqual(12, callback.story_id)

    def test_engagement_labels_follow_current_user_state(self) -> None:
        state = PublicMediaState(
            like_count=5,
            liked_by_user=True,
            subscribed=True,
        )
        keyboard = build_public_archive_keyboard(
            self.page,
            state,
            viewer_user_id=100,
        )
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("❤️ 5", labels)
        self.assertIn("🔕 Отписаться", labels)
        self.assertIn("Отметок: <b>5</b>", format_public_archive_caption(self.page, state))

    def test_download_button_is_hidden_from_regular_viewer(self) -> None:
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
