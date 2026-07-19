from __future__ import annotations

import importlib
import unittest
from pathlib import Path


ALIASES = {
    "velvet_bot.handlers.admin_directory": (
        "velvet_bot.presentation.telegram.routers.characters.directory"
    ),
    "velvet_bot.handlers.admin_stories": (
        "velvet_bot.presentation.telegram.routers.stories.management"
    ),
    "velvet_bot.handlers.admin_uncategorized": (
        "velvet_bot.presentation.telegram.routers.characters.uncategorized"
    ),
    "velvet_bot.handlers.admin_universe_story_flow": (
        "velvet_bot.presentation.telegram.routers.stories.universe_flow"
    ),
    "velvet_bot.handlers.character_aliases": (
        "velvet_bot.presentation.telegram.routers.characters.aliases"
    ),
    "velvet_bot.handlers.characters": (
        "velvet_bot.presentation.telegram.routers.characters.profiles"
    ),
    "velvet_bot.handlers.kr_profile_overrides": (
        "velvet_bot.presentation.telegram.routers.characters.kr_profile_overrides"
    ),
    "velvet_bot.handlers.kr_universe_entry": (
        "velvet_bot.presentation.telegram.routers.stories.kr_universe_entry"
    ),
    "velvet_bot.handlers.multi_story_kr": (
        "velvet_bot.presentation.telegram.routers.stories.multi_story_kr"
    ),
}


class P3CCharactersStoriesPresentationTests(unittest.TestCase):
    def test_legacy_imports_resolve_to_canonical_module_objects(self) -> None:
        for legacy_name, canonical_name in ALIASES.items():
            with self.subTest(legacy=legacy_name):
                legacy = importlib.import_module(legacy_name)
                canonical = importlib.import_module(canonical_name)
                self.assertIs(legacy, canonical)

    def test_legacy_files_are_only_module_aliases(self) -> None:
        for legacy_name, canonical_name in ALIASES.items():
            with self.subTest(legacy=legacy_name):
                path = Path(*legacy_name.split(".")).with_suffix(".py")
                source = path.read_text(encoding="utf-8")
                self.assertIn("P3_COMPAT_MODULE_ALIAS", source)
                self.assertIn(canonical_name, source)
                self.assertNotIn("@router.", source)
                self.assertLessEqual(len(source.splitlines()), 8)

    def test_canonical_controllers_own_router_implementations(self) -> None:
        for canonical_name in ALIASES.values():
            with self.subTest(canonical=canonical_name):
                path = Path(*canonical_name.split(".")).with_suffix(".py")
                source = path.read_text(encoding="utf-8")
                self.assertIn("router = Router(name=__name__)", source)

    def test_active_composition_uses_canonical_paths(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        for legacy_name, canonical_name in ALIASES.items():
            self.assertNotIn(legacy_name, source)
            self.assertIn(canonical_name, source)


if __name__ == "__main__":
    unittest.main()
