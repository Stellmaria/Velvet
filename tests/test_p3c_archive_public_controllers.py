from __future__ import annotations

import importlib
import unittest
from pathlib import Path


ALIASES = {
    "velvet_bot.handlers.admin_large_media_preview": (
        "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.admin_large_media_preview"
    ),
    "velvet_bot.handlers.admin_media_display": (
        "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.admin_media_display"
    ),
    "velvet_bot.handlers.admin_media_spoiler": (
        "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.admin_media_spoiler"
    ),
    "velvet_bot.handlers.archive": (
        "velvet_bot.presentation.telegram.routers.archive.save"
    ),
    "velvet_bot.handlers.discussion_updates": (
        "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.discussion_updates"
    ),
    "velvet_bot.handlers.guest_archive": (
        "velvet_bot.presentation.telegram.routers.archive.guest"
    ),
    "velvet_bot.handlers.inline_help": (
        "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.inline_help"
    ),
    "velvet_bot.handlers.media_browser": (
        "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.media_browser"
    ),
    "velvet_bot.handlers.media_prompt_binding": (
        "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.media_prompt_binding"
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
    "velvet_bot.handlers.spoiler_save": (
        "velvet_bot.presentation.telegram.routers.archive.spoiler"
    ),
    "velvet_bot.handlers.start": (
        "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.start"
    ),
    "velvet_bot.handlers.telegram_analytics_import": (
        "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.telegram_analytics_import"
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
                self.assertIn("router = Router", source)
                self.assertIn("@router.", source)

    def test_active_composition_uses_canonical_paths(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        for legacy_name, canonical_name in ALIASES.items():
            self.assertIn(canonical_name, source)
            self.assertNotIn(f"from {legacy_name} import", source)

    def test_new_controller_include_order_is_preserved(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        includes = (
            "router.include_router(telegram_analytics_import_router)",
            "router.include_router(discussion_updates_router)",
            "router.include_router(start_router)",
            "router.include_router(media_prompt_binding_router)",
            "router.include_router(admin_media_spoiler_router)",
            "router.include_router(admin_large_media_preview_router)",
            "router.include_router(admin_media_display_router)",
            "router.include_router(media_browser_router)",
            "router.include_router(inline_help_router)",
        )
        positions = [source.index(item) for item in includes]
        self.assertEqual(positions, sorted(positions))

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
