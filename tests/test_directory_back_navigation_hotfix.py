from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace

from velvet_bot.presentation.telegram.routers.characters import kr_profile_overrides
from velvet_bot.presentation.telegram.routers.characters.directory import (
    AdminDirectoryCallback,
)
from velvet_bot.presentation.telegram.routers.characters.navigation import (
    resolve_directory_category,
)
from velvet_bot.presentation.telegram.routers.characters.rename import (
    InvalidDirectoryCategoryFilter,
    _keyboard_with_rename,
)


class DirectoryBackNavigationHotfixTests(unittest.IsolatedAsyncioTestCase):
    def test_category_resolver_prefers_valid_callback_value(self) -> None:
        self.assertEqual(resolve_directory_category("Мужской", "female"), "male")

    def test_category_resolver_falls_back_to_current_character_category(self) -> None:
        self.assertEqual(resolve_directory_category("kr", "female"), "female")
        self.assertEqual(resolve_directory_category("", "male"), "male")

    def test_category_resolver_has_safe_uncategorized_fallback(self) -> None:
        self.assertEqual(resolve_directory_category("stale", None), "uncategorized")

    def test_profile_back_button_carries_canonical_category_and_character(self) -> None:
        item = SimpleNamespace(
            character=SimpleNamespace(id=77, name="Кайн"),
            category="male",
            universe=None,
            media_count=0,
            prompt_post_url=None,
        )

        keyboard = _keyboard_with_rename(item, category="", page=3)
        packed = keyboard.inline_keyboard[-1][0].callback_data
        callback = AdminDirectoryCallback.unpack(packed)

        self.assertEqual(callback.action, "menu")
        self.assertEqual(callback.category, "male")
        self.assertEqual(callback.page, 3)
        self.assertEqual(callback.character_id, 77)

    async def test_only_invalid_menu_categories_are_intercepted(self) -> None:
        category_filter = InvalidDirectoryCategoryFilter()

        self.assertTrue(
            await category_filter(
                SimpleNamespace(),
                AdminDirectoryCallback(action="menu", category=""),
            )
        )
        self.assertTrue(
            await category_filter(
                SimpleNamespace(),
                AdminDirectoryCallback(action="menu", category="kr"),
            )
        )
        self.assertFalse(
            await category_filter(
                SimpleNamespace(),
                AdminDirectoryCallback(action="menu", category="Мужской"),
            )
        )
        self.assertFalse(
            await category_filter(
                SimpleNamespace(),
                AdminDirectoryCallback(action="menu", category="uncategorized"),
            )
        )

    def test_touched_kr_controller_uses_canonical_imports(self) -> None:
        source = inspect.getsource(kr_profile_overrides)
        self.assertNotIn("velvet_bot.handlers.", source)


if __name__ == "__main__":
    unittest.main()
