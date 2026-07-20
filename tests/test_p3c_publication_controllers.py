from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETIRED_ALIASES = {
    "velvet_bot.handlers.publication_center": (
        "velvet_bot.presentation.telegram.routers.publication.center"
    ),
    "velvet_bot.handlers.publication_center_safe": (
        "velvet_bot.presentation.telegram.routers.publication.safe"
    ),
}


class P3CPublicationControllersTests(unittest.TestCase):
    def test_retired_legacy_files_are_removed(self) -> None:
        for legacy_name in RETIRED_ALIASES:
            with self.subTest(legacy=legacy_name):
                path = ROOT / Path(*legacy_name.split(".")).with_suffix(".py")
                self.assertFalse(path.exists())

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
        self.assertEqual(34, source.count("router.include_router("))


if __name__ == "__main__":
    unittest.main()
