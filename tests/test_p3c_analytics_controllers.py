from __future__ import annotations

import importlib
import unittest
from pathlib import Path


CHANNEL_ALIAS = "velvet_bot.handlers.channel_analytics"
CHANNEL_CANONICAL = (
    "velvet_bot.presentation.telegram.routers.analytics_controllers.channel"
)
RETIRED_ALIAS_NAMES = (
    "analytics_dashboard",
    "analytics_dashboard_overrides",
    "analytics_discussion_overrides",
    "analytics_management",
    "analytics_management_aliases",
    "analytics_management_common",
    "analytics_management_publications",
    "analytics_management_tags",
)
CANONICAL_MODULES = (
    CHANNEL_CANONICAL,
    "velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard_overrides",
    "velvet_bot.presentation.telegram.routers.analytics_controllers.discussion_overrides",
    "velvet_bot.presentation.telegram.routers.analytics_controllers.management",
    "velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard",
    "velvet_bot.presentation.telegram.routers.analytics_controllers.management_common",
    "velvet_bot.presentation.telegram.routers.analytics_controllers.management_tags",
    "velvet_bot.presentation.telegram.routers.analytics_controllers.management_aliases",
    "velvet_bot.presentation.telegram.routers.analytics_controllers.management_publications",
)


class P3CAnalyticsControllersTests(unittest.TestCase):
    def test_deferred_channel_alias_still_resolves_to_canonical_module(self) -> None:
        self.assertIs(
            importlib.import_module(CHANNEL_ALIAS),
            importlib.import_module(CHANNEL_CANONICAL),
        )

    def test_deferred_channel_file_is_only_module_alias(self) -> None:
        path = Path(*CHANNEL_ALIAS.split(".")).with_suffix(".py")
        source = path.read_text(encoding="utf-8")
        self.assertIn("P3_COMPAT_MODULE_ALIAS", source)
        self.assertIn(CHANNEL_CANONICAL, source)
        self.assertNotIn("@router.", source)
        self.assertLessEqual(len(source.splitlines()), 10)

    def test_other_analytics_alias_files_are_retired(self) -> None:
        for name in RETIRED_ALIAS_NAMES:
            with self.subTest(alias=name):
                self.assertFalse(Path("velvet_bot/handlers", f"{name}.py").exists())

    def test_canonical_controllers_own_router_implementations(self) -> None:
        router_modules = CANONICAL_MODULES[:5]
        for canonical_name in router_modules:
            with self.subTest(canonical=canonical_name):
                path = Path(*canonical_name.split(".")).with_suffix(".py")
                source = path.read_text(encoding="utf-8")
                self.assertIn("router = Router(name=__name__)", source)

    def test_active_composition_uses_canonical_paths_in_original_order(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/routers/analytics.py"
        ).read_text(encoding="utf-8")
        legacy_prefix = "velvet_bot." + "handlers."
        self.assertNotIn(legacy_prefix, source)

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
