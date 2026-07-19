from __future__ import annotations

import importlib
import unittest
from pathlib import Path


ALIASES = {
    "velvet_bot.handlers.reference_comparison_help": (
        "velvet_bot.presentation.telegram.routers.references.comparison_help"
    ),
    "velvet_bot.handlers.reference_comparison": (
        "velvet_bot.presentation.telegram.routers.references.comparison"
    ),
    "velvet_bot.handlers.reference_documents": (
        "velvet_bot.presentation.telegram.routers.references.documents"
    ),
    "velvet_bot.handlers.reference_albums": (
        "velvet_bot.presentation.telegram.routers.references.albums"
    ),
    "velvet_bot.handlers.reference_management": (
        "velvet_bot.presentation.telegram.routers.references.management"
    ),
    "velvet_bot.handlers.references": (
        "velvet_bot.presentation.telegram.routers.references.catalog"
    ),
}


class P3CReferenceControllersTests(unittest.TestCase):
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

    def test_active_composition_uses_canonical_paths_in_original_order(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        canonical_names = tuple(ALIASES.values())
        for legacy_name, canonical_name in ALIASES.items():
            self.assertNotIn(f"from {legacy_name} import", source)
            self.assertIn(f"from {canonical_name} import", source)
        positions = [source.index(name) for name in canonical_names]
        self.assertEqual(positions, sorted(positions))


if __name__ == "__main__":
    unittest.main()
