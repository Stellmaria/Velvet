from __future__ import annotations

import importlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    "velvet_bot.handlers.channel_analytics": (
        "velvet_bot.presentation.telegram.routers.analytics_controllers.channel"
    ),
    "velvet_bot.handlers.analytics_dashboard": (
        "velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard"
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
                path = ROOT / Path(*legacy_name.split(".")).with_suffix(".py")
                source = path.read_text(encoding="utf-8")
                self.assertIn("P3_COMPAT_MODULE_ALIAS", source)
                self.assertIn(canonical_name, source)
                self.assertNotIn("@router.", source)
                self.assertLessEqual(len(source.splitlines()), 10)

    def test_canonical_modules_own_analytics_handlers(self) -> None:
        root = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/analytics_controllers"
        )
        channel = (root / "channel.py").read_text(encoding="utf-8")
        dashboard = (root / "dashboard.py").read_text(encoding="utf-8")
        dashboard_overrides = (root / "dashboard_overrides.py").read_text(
            encoding="utf-8"
        )
        discussion_overrides = (root / "discussion_overrides.py").read_text(
            encoding="utf-8"
        )
        management = (root / "management.py").read_text(encoding="utf-8")

        self.assertIn("@router.channel_post()", channel)
        self.assertIn('Command("channelstats", "stats")', channel)
        self.assertIn('Command("analytics", "analyticsmenu")', dashboard)
        self.assertIn("AnalyticsCallback.filter()", dashboard)
        self.assertIn("DashboardLinkCallback.filter", dashboard_overrides)
        self.assertIn(
            'class DiscussionInsightCallback(CallbackData, prefix="d5")',
            discussion_overrides,
        )
        self.assertIn("AnalyticsManageCallback.filter()", management)
        self.assertIn("handle_alias_reply_message", management)

    def test_analytics_bundle_uses_only_canonical_controllers(self) -> None:
        path = ROOT / "velvet_bot/presentation/telegram/routers/analytics.py"
        source = path.read_text(encoding="utf-8")
        for canonical_name in ALIASES.values():
            self.assertIn(f"from {canonical_name} import", source)
        self.assertNotIn("from velvet_bot.handlers.", source)
        self.assertEqual(5, source.count("router.include_router("))


if __name__ == "__main__":
    unittest.main()
