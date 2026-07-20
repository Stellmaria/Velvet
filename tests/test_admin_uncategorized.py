import unittest
from datetime import UTC, datetime

from velvet_bot.character_directory import CharacterDirectoryItem, CharacterDirectoryPage
from velvet_bot.database import Character
from velvet_bot.presentation.telegram.routers.characters.contracts import (
    AdminDirectoryCallback,
)
from velvet_bot.presentation.telegram.routers.characters.uncategorized import (
    build_category_picker,
    build_uncategorized_keyboard,
    build_universe_picker,
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
            universe=None,
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
        self.assertIn("👥 Пол / состав", labels)

        picker_button = next(
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.text == "👥 Пол / состав"
        )
        callback = AdminDirectoryCallback.unpack(picker_button.callback_data)
        self.assertEqual("pickcat", callback.action)
        self.assertEqual(self.character.id, callback.character_id)
        self.assertEqual("uncategorized", callback.category)

    def test_category_picker_contains_all_six_values(self) -> None:
        keyboard = build_category_picker(self.item, page=0)
        buttons = [
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
            and AdminDirectoryCallback.unpack(button.callback_data).action == "setcat"
        ]
        callbacks = [
            AdminDirectoryCallback.unpack(button.callback_data) for button in buttons
        ]
        self.assertEqual(
            {"female", "male", "mf", "mfm", "mm", "ff"},
            {callback.category for callback in callbacks},
        )
        self.assertIn("👨‍👩‍👨 МЖМ", {button.text for button in buttons})
        self.assertTrue(all(callback.character_id == self.character.id for callback in callbacks))

    def test_universe_picker_contains_top_level_values(self) -> None:
        keyboard = build_universe_picker(
            self.item,
            page=0,
            return_category="male",
        )
        callbacks = [
            AdminDirectoryCallback.unpack(button.callback_data)
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
            and AdminDirectoryCallback.unpack(button.callback_data).action == "setuni"
        ]
        self.assertEqual(
            {"shs", "kr", "lm", "idm", "games", "lagerta", "original", "other"},
            {callback.universe for callback in callbacks},
        )
        self.assertNotIn("bg3", {callback.universe for callback in callbacks})
        self.assertNotIn("re", {callback.universe for callback in callbacks})
        self.assertTrue(all(callback.return_category == "male" for callback in callbacks))


if __name__ == "__main__":
    unittest.main()
