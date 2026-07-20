from __future__ import annotations

import importlib
import unittest
from pathlib import Path


CANONICAL_MODULES = (
    "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.admin_large_media_preview",
    "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.admin_media_display",
    "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.admin_media_spoiler",
    "velvet_bot.presentation.telegram.routers.archive.save",
    "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.discussion_updates",
    "velvet_bot.presentation.telegram.routers.archive.guest",
    "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.inline_help",
    "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.media_browser",
    "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.media_prompt_binding",
    "velvet_bot.presentation.telegram.routers.public_archive.catalog",
    "velvet_bot.presentation.telegram.routers.public_archive.manager",
    "velvet_bot.presentation.telegram.routers.public_archive.media_display",
    "velvet_bot.presentation.telegram.routers.public_archive.notification_open",
    "velvet_bot.presentation.telegram.routers.archive.spoiler",
    "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.start",
    "velvet_bot.presentation.telegram.routers.archive_and_public_controllers.telegram_analytics_import",
)

RETIRED_ALIASES = (
    "admin_large_media_preview",
    "admin_media_display",
    "admin_media_spoiler",
    "archive",
    "discussion_updates",
    "guest_archive",
    "inline_help",
    "media_browser",
    "media_prompt_binding",
    "public_archive",
    "public_manager",
    "public_media_display",
    "public_notification_open",
    "spoiler_save",
    "start",
    "telegram_analytics_import",
)


class P3CArchivePublicControllersTests(unittest.TestCase):
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
                self.assertIn("router = Router", source)
                self.assertIn("@router.", source)

    def test_active_composition_uses_canonical_paths(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        for module_name in CANONICAL_MODULES:
            self.assertIn(module_name, source)

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
