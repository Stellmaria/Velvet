import unittest
from datetime import UTC, datetime

from velvet_bot.character_directory import (
    CategorySummary,
    CharacterDirectoryItem,
    CharacterDirectoryPage,
    normalize_universe_category,
)
from velvet_bot.database import Character
from velvet_bot.handlers.admin_directory import _profile_keyboard, _universe_picker
from velvet_bot.public_ui import (
    PublicArchiveCallback,
    build_public_character_menu,
    build_public_filter_menu,
    decode_public_filter,
    encode_public_filter,
)


class UniverseCategoryTests(unittest.TestCase):
    def test_universe_aliases_are_normalized(self) -> None:
        self.assertEqual("shs", normalize_universe_category("SHS"))
        self.assertEqual("kr", normalize_universe_category("КР"))
        self.assertEqual("lm", normalize_universe_category("лм"))
        self.assertEqual("lagerta", normalize_universe_category("Лагерта"))
        self.assertEqual("original", normalize_universe_category("Original"))

    def test_uncategorized_universe_is_owner_only_option(self) -> None:
        self.assertEqual(
            "uncategorized",
            normalize_universe_category("без", allow_uncategorized=True),
        )
        with self.assertRaises(ValueError):
            normalize_universe_category("без")


class TwoAxisFilterUiTests(unittest.TestCase):
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
        self.item = CharacterDirectoryItem(
            character=self.character,
            category="male",
            prompt_post_url=None,
            media_count=3,
            universe_category="kr",
        )

    def test_filter_codec_preserves_old_single_category_value(self) -> None:
        self.assertEqual("male", encode_public_filter("male", ""))
        self.assertEqual(("male", ""), decode_public_filter("male"))

    def test_filter_codec_combines_type_and_universe(self) -> None:
        packed = encode_public_filter("male", "kr")
        self.assertEqual(("male", "kr"), decode_public_filter(packed))

    def test_public_filter_menu_builds_combined_show_button(self) -> None:
        keyboard = build_public_filter_menu(
            [CategorySummary("male", "Мужской", "👨", 4)],
            [CategorySummary("kr", "КР", "💎", 3)],
            selected_category="male",
            selected_universe="kr",
        )
        show_button = next(
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.text == "🔎 Показать персонажей"
        )
        callback = PublicArchiveCallback.unpack(show_button.callback_data)
        self.assertEqual("menu", callback.action)
        self.assertEqual(("male", "kr"), decode_public_filter(callback.category))

    def test_character_page_keeps_combined_filter_in_callbacks(self) -> None:
        page = CharacterDirectoryPage(
            items=[self.item],
            category="male",
            page=0,
            page_size=6,
            total_characters=1,
            universe_category="kr",
        )
        keyboard = build_public_character_menu(page)
        callback = PublicArchiveCallback.unpack(
            keyboard.inline_keyboard[0][0].callback_data
        )
        self.assertEqual(("male", "kr"), decode_public_filter(callback.category))

    def test_owner_profile_has_universe_picker(self) -> None:
        keyboard = _profile_keyboard(self.item, scope="male", page=0)
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("🌐 Выбрать вселенную", labels)

    def test_universe_picker_contains_all_requested_categories(self) -> None:
        keyboard = _universe_picker(self.item, scope="male", page=0)
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("🔹 SHS", labels)
        self.assertIn("💎 КР", labels)
        self.assertIn("🌙 ЛМ", labels)
        self.assertIn("🛡 Лагерта", labels)
        self.assertIn("✦ Original", labels)


if __name__ == "__main__":
    unittest.main()
