from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDLERS = ROOT / "velvet_bot/handlers"
RETIRED = {"publication_center", "publication_center_safe"}


class P3CPublicationControllersTests(unittest.TestCase):
    def test_retired_legacy_files_are_removed(self) -> None:
        for alias_name in RETIRED:
            with self.subTest(alias=alias_name):
                self.assertFalse((HANDLERS / f"{alias_name}.py").exists())

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

    def test_bundle_keeps_workspace_and_legacy_publication_before_archive(self) -> None:
        path = ROOT / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn(
            "from velvet_bot.presentation.telegram.routers.publication.safe import (",
            source,
        )
        self.assertLess(
            source.index("router.include_router(workspace_publications_router)"),
            source.index("router.include_router(publication_center_router)"),
        )
        self.assertLess(
            source.index("router.include_router(publication_center_router)"),
            source.index("router.include_router(archive_router)"),
        )
        self.assertEqual(49, source.count("router.include_router("))


if __name__ == "__main__":
    unittest.main()
