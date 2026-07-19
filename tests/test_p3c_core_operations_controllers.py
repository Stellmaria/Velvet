from __future__ import annotations

import importlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    "velvet_bot.handlers.error_center": (
        "velvet_bot.presentation.telegram.routers.core_operations_controllers.error_center"
    ),
    "velvet_bot.handlers.owner_actions": (
        "velvet_bot.presentation.telegram.routers.core_operations_controllers.owner_actions"
    ),
    "velvet_bot.handlers.owner_menu": (
        "velvet_bot.presentation.telegram.routers.core_operations_controllers.owner_menu"
    ),
}


class P3CCoreOperationsControllersTests(unittest.TestCase):
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

    def test_canonical_modules_own_core_handlers(self) -> None:
        root = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers"
        )
        error_center = (root / "error_center.py").read_text(encoding="utf-8")
        owner_actions = (root / "owner_actions.py").read_text(encoding="utf-8")
        owner_menu = (root / "owner_menu.py").read_text(encoding="utf-8")

        self.assertIn('Command("test_error_alert")', error_center)
        self.assertIn('F.data.startswith("err:ack:")', error_center)
        self.assertIn("OwnerActionCallback.filter()", owner_actions)
        self.assertIn("class OwnerActionReplyFilter", owner_actions)
        self.assertIn('Command("menu", "admin")', owner_menu)
        self.assertIn("OwnerMenuCallback.filter()", owner_menu)
        self.assertIn("router.include_router(watermark_router)", owner_menu)

    def test_core_bundle_uses_canonical_controllers_in_original_order(self) -> None:
        path = ROOT / "velvet_bot/presentation/telegram/routers/core_operations.py"
        source = path.read_text(encoding="utf-8")
        for legacy_name, canonical_name in ALIASES.items():
            self.assertNotIn(legacy_name, source)
            self.assertIn(canonical_name, source)

        includes = [
            "router.include_router(error_center_router)",
            "router.include_router(owner_actions_router)",
            "router.include_router(owner_menu_router)",
            "router.include_router(supervisor_control_router)",
            "router.include_router(system_center_router)",
        ]
        positions = [source.index(item) for item in includes]
        self.assertEqual(positions, sorted(positions))


if __name__ == "__main__":
    unittest.main()
