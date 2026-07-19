from __future__ import annotations

import importlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    "velvet_bot.handlers.publication_center": (
        "velvet_bot.presentation.telegram.routers.publication.center"
    ),
    "velvet_bot.handlers.publication_center_safe": (
        "velvet_bot.presentation.telegram.routers.publication.safe"
    ),
}


class P3CPublicationControllersTests(unittest.TestCase):
    def test_legacy_imports_resolve_to_canonical_module_objects(self) -> None:
        for legacy_name, canonical_name in ALIASES.items():
            with self.subTest(legacy=legacy_name):
                legacy = importlib.import_module(legacy_name)
                canonical = importlib.import_module(canonical_name)
                self.assertIs(legacy, canonical)

    def test_legacy_files_are_only_module_aliases(self) -> None:
        for legacy_name, canonical_name in ALIASES.items():
            with self.subTest(legacy=legacy_name):
                path = ROOT / Path(*legacy_name.split(".")).with_suffix(".py")
                source = path.read_text(encoding="utf-8")
                self.assertIn("P3_COMPAT_MODULE_ALIAS", source)
                self.assertIn(canonical_name, source)
                self.assertNotIn("@router.", source)
                self.assertLessEqual(len(source.splitlines()), 10)

    def test_canonical_center_owns_publication_handlers(self) -> None:
        path = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/publication/center.py"
        )
        source = path.read_text(encoding="utf-8")
        self.assertIn('class PublicationCallback(CallbackData, prefix="pubq")', source)
        self.assertIn('@router.message(Command("publish", "publishing", "publications"))', source)
        self.assertIn('@router.message(Command("checkpost"))', source)
        self.assertIn("async def handle_publication_callback", source)
        self.assertIn("async def capture_private_publication_input", source)

    def test_safe_router_depends_on_canonical_center(self) -> None:
        path = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/publication/safe.py"
        )
        source = path.read_text(encoding="utf-8")
        self.assertIn(
            "from velvet_bot.presentation.telegram.routers.publication.center import (",
            source,
        )
        self.assertNotIn("from velvet_bot.handlers.publication_center", source)

    def test_bundle_keeps_publication_before_archive_catch_all(self) -> None:
        path = ROOT / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn(
            "from velvet_bot.presentation.telegram.routers.publication.safe import (",
            source,
        )
        self.assertLess(
            source.index("router.include_router(publication_center_router)"),
            source.index("router.include_router(archive_router)"),
        )
        self.assertEqual(32, source.count("router.include_router("))


if __name__ == "__main__":
    unittest.main()
