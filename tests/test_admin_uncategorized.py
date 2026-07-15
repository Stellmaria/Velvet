import unittest
from datetime import UTC, datetime

from velvet_bot.character_directory import CharacterDirectoryItem, CharacterDirectoryPage
from velvet_bot.database import Character
from velvet_bot.handlers.admin_directory import AdminDirectoryCallback
from velvet_bot.handlers.admin_uncategorized import (
    build_category_picker,
    build_uncategorized_keyboard,
)


class AdminUncategorizedUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.character = Character(
            id=17,
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
            category=None,
            prompt_post_url=None,
            media_count=4,
        )
        self.page = CharacterDirectoryPage(
            items=[self.item],
            category="uncategorized",
            page=0,
            page_size=6,
            total_characters=1,
        )

    def test_uncategorized_row_has_category_picker_button(self) -> None:
        keyboard = build_uncategorized_keyboard(self.page)
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("🏷 Категория", labels)

        picker_button = next(
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.text == "🏷 Категория"
        )
        callback = AdminDirectoryCallback.unpack(picker_button.callback_data)
        self.assertEqual("pickcat", callback.action)
        self.assertEqual(self.character.id, callback.character_id)
        self.assertEqual("uncategorized", callback.category)

    def test_picker_contains_all_five_categories(self) -> None:
        keyboard = build_category_picker(self.item, page=0)
        callbacks = [
            AdminDirectoryCallback.unpack(button.callback_data)
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
            and AdminDirectoryCallback.unpack(button.callback_data).action == "setcat"
        ]
        self.assertEqual(
            {"female", "male", "mf", "mm", "ff"},
            {callback.category for callback in callbacks},
        )
        self.assertTrue(all(callback.character_id == self.character.id for callback in callbacks))


if __name__ == "__main__":
    unittest.main()
