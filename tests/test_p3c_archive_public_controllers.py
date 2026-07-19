from __future__ import annotations

import importlib
import unittest
from pathlib import Path


ALIASES = {
    "velvet_bot.handlers.archive": (
        "velvet_bot.presentation.telegram.routers.archive.save"
    ),
    "velvet_bot.handlers.guest_archive": (
        "velvet_bot.presentation.telegram.routers.archive.guest"
    ),
    "velvet_bot.handlers.spoiler_save": (
        "velvet_bot.presentation.telegram.routers.archive.spoiler"
    ),
    "velvet_bot.handlers.public_archive": (
        "velvet_bot.presentation.telegram.routers.public_archive.catalog"
    ),
    "velvet_bot.handlers.public_manager": (
        "velvet_bot.presentation.telegram.routers.public_archive.manager"
    ),
    "velvet_bot.handlers.public_media_display": (
        "velvet_bot.presentation.telegram.routers.public_archive.media_display"
    ),
    "velvet_bot.handlers.public_notification_open": (
        "velvet_bot.presentation.telegram.routers.public_archive.notification_open"
    ),
}


class P3CArchivePublicControllersTests(unittest.TestCase):
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
                self.assertLessEqual(len(source.splitlines()), 10)

    def test_canonical_controllers_own_router_implementations(self) -> None:
        for canonical_name in ALIASES.values():
            with self.subTest(canonical=canonical_name):
                path = Path(*canonical_name.split(".")).with_suffix(".py")
                source = path.read_text(encoding="utf-8")
                self.assertIn("router = Router(name=__name__)", source)
                self.assertIn("@router.", source)

    def test_active_composition_uses_canonical_paths_in_existing_order(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        positions = []
        for canonical_name in (
            "velvet_bot.presentation.telegram.routers.public_archive.media_display",
            "velvet_bot.presentation.telegram.routers.public_archive.manager",
            "velvet_bot.presentation.telegram.routers.public_archive.notification_open",
            "velvet_bot.presentation.telegram.routers.public_archive.catalog",
            "velvet_bot.presentation.telegram.routers.archive.guest",
            "velvet_bot.presentation.telegram.routers.archive.spoiler",
            "velvet_bot.presentation.telegram.routers.archive.save",
        ):
            self.assertIn(canonical_name, source)
            positions.append(source.index(canonical_name))
        self.assertEqual(positions, sorted(positions))
        for legacy_name in ALIASES:
            self.assertNotIn(f"from {legacy_name} import", source)

    def test_publication_stays_before_archive_catch_all(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        self.assertLess(
            source.index("router.include_router(publication_center_router)"),
            source.index("router.include_router(archive_router)"),
        )


if __name__ == "__main__":
    unittest.main()
