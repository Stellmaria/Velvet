from __future__ import annotations

import importlib
import unittest
from pathlib import Path


ALIASES = {
    "velvet_bot.handlers.channel_analytics": (
        "velvet_bot.presentation.telegram.routers.analytics_controllers.channel"
    ),
    "velvet_bot.handlers.analytics_dashboard_overrides": (
        "velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard_overrides"
    ),
    "velvet_bot.handlers.analytics_discussion_overrides": (
        "velvet_bot.presentation.telegram.routers.analytics_controllers.discussion_overrides"
    ),
    "velvet_bot.handlers.analytics_management": (
        "velvet_bot.presentation.telegram.routers.analytics_controllers.management"
    ),
    "velvet_bot.handlers.analytics_dashboard": (
        "velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard"
    ),
    "velvet_bot.handlers.analytics_management_common": (
        "velvet_bot.presentation.telegram.routers.analytics_controllers.management_common"
    ),
    "velvet_bot.handlers.analytics_management_tags": (
        "velvet_bot.presentation.telegram.routers.analytics_controllers.management_tags"
    ),
    "velvet_bot.handlers.analytics_management_aliases": (
        "velvet_bot.presentation.telegram.routers.analytics_controllers.management_aliases"
    ),
    "velvet_bot.handlers.analytics_management_publications": (
        "velvet_bot.presentation.telegram.routers.analytics_controllers.management_publications"
    ),
}


class P3CAnalyticsControllersTests(unittest.TestCase):
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
        router_modules = {
            "velvet_bot.presentation.telegram.routers.analytics_controllers.channel",
            "velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard_overrides",
            "velvet_bot.presentation.telegram.routers.analytics_controllers.discussion_overrides",
            "velvet_bot.presentation.telegram.routers.analytics_controllers.management",
            "velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard",
        }
        for canonical_name in router_modules:
            with self.subTest(canonical=canonical_name):
                path = Path(*canonical_name.split(".")).with_suffix(".py")
                source = path.read_text(encoding="utf-8")
                self.assertIn("router = Router(name=__name__)", source)

    def test_active_composition_uses_canonical_paths_in_original_order(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/analytics.py"
        ).read_text(encoding="utf-8")
        for legacy_name in (
            "velvet_bot.handlers.channel_analytics",
            "velvet_bot.handlers.analytics_dashboard_overrides",
            "velvet_bot.handlers.analytics_discussion_overrides",
            "velvet_bot.handlers.analytics_management",
            "velvet_bot.handlers.analytics_dashboard",
        ):
            self.assertNotIn(legacy_name, source)

        includes = [
            "router.include_router(channel_analytics_router)",
            "router.include_router(analytics_dashboard_overrides_router)",
            "router.include_router(analytics_discussion_overrides_router)",
            "router.include_router(analytics_management_router)",
            "router.include_router(analytics_dashboard_router)",
        ]
        positions = [source.index(item) for item in includes]
        self.assertEqual(positions, sorted(positions))


if __name__ == "__main__":
    unittest.main()
