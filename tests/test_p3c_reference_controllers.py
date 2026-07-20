from __future__ import annotations

import importlib
import unittest
from pathlib import Path


CANONICAL_MODULES = (
    "velvet_bot.presentation.telegram.routers.references.comparison_help",
    "velvet_bot.presentation.telegram.routers.references.comparison",
    "velvet_bot.presentation.telegram.routers.references.documents",
    "velvet_bot.presentation.telegram.routers.references.albums",
    "velvet_bot.presentation.telegram.routers.references.management",
    "velvet_bot.presentation.telegram.routers.references.catalog",
)

RETIRED_ALIASES = (
    "reference_comparison_help",
    "reference_comparison",
    "reference_documents",
    "reference_albums",
    "reference_management",
    "references",
)


class P3CReferenceControllersTests(unittest.TestCase):
    def test_canonical_modules_import_directly(self) -> None:
        for module_name in CANONICAL_MODULES:
            with self.subTest(module=module_name):
                self.assertIsNotNone(importlib.import_module(module_name))

    def test_retired_handler_alias_files_are_absent(self) -> None:
        for name in RETIRED_ALIASES:
            with self.subTest(alias=name):
                self.assertFalse(Path("velvet_bot/handlers", f"{name}.py").exists())

    def test_canonical_controllers_own_router_implementations(self) -> None:
        for module_name in CANONICAL_MODULES:
            with self.subTest(module=module_name):
                path = Path(*module_name.split(".")).with_suffix(".py")
                source = path.read_text(encoding="utf-8")
                self.assertIn("router = Router(name=__name__)", source)

    def test_active_composition_uses_canonical_paths_in_original_order(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        for module_name in CANONICAL_MODULES:
            self.assertIn(f"from {module_name} import", source)
        positions = [source.index(name) for name in CANONICAL_MODULES]
        self.assertEqual(positions, sorted(positions))


if __name__ == "__main__":
    unittest.main()
