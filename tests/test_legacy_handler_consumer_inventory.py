from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path

from velvet_bot.presentation.telegram.routers.characters.contracts import (
    AdminDirectoryCallback,
)
from velvet_bot.presentation.telegram.routers.characters.directory import (
    AdminDirectoryCallback as DirectoryCallbackExport,
)
from velvet_bot.presentation.telegram.routers.stories.contracts import (
    AdminStoryCallback,
)
from velvet_bot.presentation.telegram.routers.stories.management import (
    AdminStoryCallback as StoryCallbackExport,
)


class LegacyHandlerConsumerInventoryTests(unittest.TestCase):
    def test_inventory_matches_current_tree(self) -> None:
        subprocess.run(
            [
                sys.executable,
                "scripts/inventory_legacy_handler_consumers.py",
                "--check",
                "--label",
                "p3d-production-legacy-zero",
            ],
            check=True,
        )


    def test_production_tree_has_no_legacy_handler_consumers(self) -> None:
        source = Path("docs/legacy_handler_consumer_inventory.json").read_text(
            encoding="utf-8"
        )
        self.assertIn('"consumer_file_count": 0', source)
        self.assertIn('"legacy_reference_count": 0', source)
        self.assertIn('"legacy_module_count": 0', source)

    def test_cleaned_character_story_controllers_use_public_contracts(self) -> None:
        for relative in (
            "velvet_bot/presentation/telegram/routers/characters/uncategorized.py",
            "velvet_bot/presentation/telegram/routers/stories/management.py",
            "velvet_bot/presentation/telegram/routers/stories/multi_story_kr.py",
        ):
            with self.subTest(path=relative):
                source = Path(relative).read_text(encoding="utf-8")
                self.assertNotIn("velvet_bot.handlers", source)
                tree = ast.parse(source, filename=relative)
                imported_names = {
                    alias.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                    for alias in node.names
                }
                self.assertNotIn("_profile_keyboard", imported_names)
                self.assertNotIn("_profile_text", imported_names)
                self.assertIn("build_character_profile_keyboard", imported_names)
                self.assertIn("format_character_profile", imported_names)

    def test_directory_keeps_callback_contract_compatibility_export(self) -> None:
        self.assertIs(AdminDirectoryCallback, DirectoryCallbackExport)
        packed = AdminDirectoryCallback(
            action="profile",
            category="male",
            page=2,
            character_id=17,
        ).pack()
        restored = DirectoryCallbackExport.unpack(packed)
        self.assertEqual("profile", restored.action)
        self.assertEqual("male", restored.category)
        self.assertEqual(2, restored.page)
        self.assertEqual(17, restored.character_id)

    def test_story_management_keeps_callback_contract_compatibility_export(self) -> None:
        self.assertIs(AdminStoryCallback, StoryCallbackExport)
        packed = AdminStoryCallback(
            action="mtoggle",
            category="female",
            directory_page=3,
            story_page=4,
            character_id=17,
            story_id=21,
        ).pack()
        restored = StoryCallbackExport.unpack(packed)
        self.assertEqual("mtoggle", restored.action)
        self.assertEqual("female", restored.category)
        self.assertEqual(3, restored.directory_page)
        self.assertEqual(4, restored.story_page)
        self.assertEqual(17, restored.character_id)
        self.assertEqual(21, restored.story_id)


if __name__ == "__main__":
    unittest.main()
