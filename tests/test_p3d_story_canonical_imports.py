from __future__ import annotations

import ast
import unittest
from pathlib import Path


TARGETS = {
    Path("velvet_bot/presentation/telegram/routers/stories/universe_flow.py"): {
        "velvet_bot.presentation.telegram.routers.characters.directory",
        "velvet_bot.presentation.telegram.routers.stories.management",
    },
    Path("velvet_bot/presentation/telegram/routers/stories/kr_universe_entry.py"): {
        "velvet_bot.presentation.telegram.routers.characters.directory",
        "velvet_bot.presentation.telegram.routers.stories.multi_story_kr",
    },
}


def _import_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


class P3DStoryCanonicalImportTests(unittest.TestCase):
    def test_cleaned_story_routers_do_not_use_handler_aliases(self) -> None:
        for path in TARGETS:
            with self.subTest(path=path):
                legacy = {
                    module
                    for module in _import_modules(path)
                    if module == "velvet_bot.handlers"
                    or module.startswith("velvet_bot.handlers.")
                }
                self.assertEqual(legacy, set())

    def test_cleaned_story_routers_use_expected_canonical_modules(self) -> None:
        for path, expected in TARGETS.items():
            with self.subTest(path=path):
                self.assertTrue(expected.issubset(_import_modules(path)))


if __name__ == "__main__":
    unittest.main()
