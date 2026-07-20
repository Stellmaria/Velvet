from __future__ import annotations

import importlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDLERS = ROOT / "velvet_bot/handlers"
MODULE_ALIAS_MARKER = "P3_COMPAT_MODULE_ALIAS"
ALIASES = {
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
RETIRED_ALIASES = {"velvet_bot.handlers.watermark"}


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

    def test_residual_legacy_imports_resolve_to_canonical_modules(self) -> None:
        for legacy_name, canonical_name in ALIASES.items():
            with self.subTest(legacy=legacy_name):
                self.assertIs(
                    importlib.import_module(legacy_name),
                    importlib.import_module(canonical_name),
                )

    def test_residual_legacy_files_are_only_aliases(self) -> None:
        for legacy_name, canonical_name in ALIASES.items():
            with self.subTest(legacy=legacy_name):
                path = ROOT / Path(*legacy_name.split(".")).with_suffix(".py")
                source = path.read_text(encoding="utf-8")
                self.assertIn(MODULE_ALIAS_MARKER, source)
                self.assertIn(canonical_name, source)
                self.assertLessEqual(len(source.splitlines()), 10)

    def test_retired_legacy_files_are_absent(self) -> None:
        for legacy_name in RETIRED_ALIASES:
            path = ROOT / Path(*legacy_name.split(".")).with_suffix(".py")
            self.assertFalse(path.exists())

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
        for legacy_name in (*ALIASES, *RETIRED_ALIASES):
            self.assertNotIn(f"from {legacy_name} import", management)
            self.assertNotIn(f"from {legacy_name} import", dashboard)
            self.assertNotIn(f"from {legacy_name} import", owner_menu)
        self.assertIn("analytics_controllers.management_tags", dashboard)
        self.assertIn("core_operations_controllers.watermark", owner_menu)


if __name__ == "__main__":
    unittest.main()
