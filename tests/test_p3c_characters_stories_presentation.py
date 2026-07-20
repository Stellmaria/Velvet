from __future__ import annotations

import importlib
import unittest
from pathlib import Path


CANONICAL_MODULES = (
    "velvet_bot.presentation.telegram.routers.characters.directory",
    "velvet_bot.presentation.telegram.routers.stories.management",
    "velvet_bot.presentation.telegram.routers.characters.uncategorized",
    "velvet_bot.presentation.telegram.routers.stories.universe_flow",
    "velvet_bot.presentation.telegram.routers.characters.aliases",
    "velvet_bot.presentation.telegram.routers.characters.profiles",
    "velvet_bot.presentation.telegram.routers.characters.kr_profile_overrides",
    "velvet_bot.presentation.telegram.routers.stories.kr_universe_entry",
    "velvet_bot.presentation.telegram.routers.stories.multi_story_kr",
)


class P3CCharactersStoriesPresentationTests(unittest.TestCase):
    def test_canonical_modules_import_and_own_routers(self) -> None:
        for module_name in CANONICAL_MODULES:
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                self.assertEqual(module_name, module.__name__)
                self.assertEqual(module_name, module.router.name)

    def test_canonical_controllers_own_router_implementations(self) -> None:
        for module_name in CANONICAL_MODULES:
            with self.subTest(module=module_name):
                path = Path(*module_name.split(".")).with_suffix(".py")
                source = path.read_text(encoding="utf-8")
                self.assertIn("router = Router(name=__name__)", source)
                self.assertNotIn("P3_COMPAT_MODULE_ALIAS", source)

    def test_active_composition_uses_canonical_paths(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("velvet_bot.handlers.", source)
        for module_name in CANONICAL_MODULES:
            self.assertIn(module_name, source)


if __name__ == "__main__":
    unittest.main()
