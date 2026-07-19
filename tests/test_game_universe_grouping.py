from __future__ import annotations

import unittest
from pathlib import Path

from velvet_bot.domains.characters.catalog import normalize_universe
from velvet_bot.domains.characters.constants import (
    GAME_UNIVERSE_ORDER,
    UNIVERSE_ORDER,
    UNIVERSE_VALUE_ORDER,
)
from velvet_bot.presentation.telegram.routers.characters.directory import (
    AdminDirectoryCallback,
)
from velvet_bot.presentation.telegram.routers.characters.game_universes import (
    _admin_game_keyboard,
)


class GameUniverseGroupingTests(unittest.TestCase):
    def test_top_level_contains_games_and_other(self) -> None:
        self.assertIn("games", UNIVERSE_ORDER)
        self.assertIn("other", UNIVERSE_ORDER)
        self.assertNotIn("bg3", UNIVERSE_ORDER)
        self.assertNotIn("re", UNIVERSE_ORDER)

    def test_stored_values_contain_game_leaves_but_not_group(self) -> None:
        self.assertEqual(GAME_UNIVERSE_ORDER, ("bg3", "re"))
        self.assertIn("bg3", UNIVERSE_VALUE_ORDER)
        self.assertIn("re", UNIVERSE_VALUE_ORDER)
        self.assertIn("other", UNIVERSE_VALUE_ORDER)
        self.assertNotIn("games", UNIVERSE_VALUE_ORDER)

    def test_text_normalization_accepts_re_and_other(self) -> None:
        self.assertEqual(normalize_universe("RE"), "re")
        self.assertEqual(normalize_universe("Resident Evil"), "re")
        self.assertEqual(normalize_universe("Другое"), "other")
        with self.assertRaises(ValueError):
            normalize_universe("Игры")

    def test_admin_game_picker_contains_only_bg3_and_re(self) -> None:
        data = AdminDirectoryCallback(
            action="setuni",
            universe="games",
            page=2,
            character_id=77,
            return_category="male",
        )
        keyboard = _admin_game_keyboard(data)
        game_buttons = keyboard.inline_keyboard[0]
        self.assertEqual([button.text for button in game_buttons], ["🎲 BG3", "🧟 RE"])
        unpacked = [AdminDirectoryCallback.unpack(button.callback_data) for button in game_buttons]
        self.assertEqual([item.action for item in unpacked], ["setgame", "setgame"])
        self.assertEqual([item.universe for item in unpacked], ["bg3", "re"])
        self.assertTrue(all(item.return_category == "male" for item in unpacked))

    def test_migration_allows_leaf_values_not_virtual_group(self) -> None:
        migration = Path("migrations/028_game_universe_grouping.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("'bg3'", migration)
        self.assertIn("'re'", migration)
        self.assertIn("'other'", migration)
        self.assertNotIn("'games'", migration)

    def test_game_router_precedes_generic_handlers(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        game_position = source.index("router.include_router(game_universes_router)")
        manager_position = source.index("router.include_router(public_manager_router)")
        uncategorized_position = source.index(
            "router.include_router(admin_uncategorized_router)"
        )
        public_archive_position = source.index(
            "router.include_router(public_archive_router)"
        )
        self.assertLess(game_position, manager_position)
        self.assertLess(game_position, uncategorized_position)
        self.assertLess(game_position, public_archive_position)


if __name__ == "__main__":
    unittest.main()
