from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDLERS = ROOT / "velvet_bot/handlers"
MODULE_ALIAS_MARKER = "P3_COMPAT_MODULE_ALIAS"
RETIRED_ALIAS_NAMES = {
    "channel_analytics",
    "watermark",
    "analytics_dashboard",
    "analytics_dashboard_overrides",
    "analytics_discussion_overrides",
    "analytics_management",
    "analytics_management_common",
    "analytics_management_tags",
    "analytics_management_aliases",
    "analytics_management_publications",
}


def residual_handler_implementations() -> set[str]:
    return {
        path.name
        for path in HANDLERS.glob("*.py")
        if path.name != "__init__.py"
        and MODULE_ALIAS_MARKER not in path.read_text(encoding="utf-8")
    }


class P3DResidualHandlerClassificationTests(unittest.TestCase):
    def test_no_physical_handler_implementations_remain(self) -> None:
        self.assertEqual(set(), residual_handler_implementations())

    def test_no_handler_aliases_remain(self) -> None:
        aliases = {
            path.stem
            for path in HANDLERS.glob("*.py")
            if path.name != "__init__.py"
            and MODULE_ALIAS_MARKER in path.read_text(encoding="utf-8")
        }
        self.assertEqual(set(), aliases)

    def test_retired_legacy_files_are_absent(self) -> None:
        for alias_name in RETIRED_ALIAS_NAMES:
            self.assertFalse((HANDLERS / f"{alias_name}.py").exists())

    def test_runtime_owners_use_canonical_paths(self) -> None:
        management = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/analytics_controllers/management.py"
        ).read_text(encoding="utf-8")
        dashboard = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/analytics_controllers/dashboard_overrides.py"
        ).read_text(encoding="utf-8")
        owner_menu = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/owner_menu.py"
        ).read_text(encoding="utf-8")
        legacy_prefix = "velvet_bot." + "handlers."
        for source in (management, dashboard, owner_menu):
            self.assertNotIn(legacy_prefix, source)
        self.assertIn("analytics_controllers.management_tags", dashboard)
        self.assertIn("core_operations_controllers.watermark", owner_menu)


if __name__ == "__main__":
    unittest.main()
