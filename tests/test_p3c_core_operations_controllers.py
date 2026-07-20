from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDLERS = ROOT / "velvet_bot/handlers"
RETIRED = {
    "error_center": (
        "velvet_bot.presentation.telegram.routers.core_operations_controllers.error_center"
    ),
    "owner_actions": (
        "velvet_bot.presentation.telegram.routers.core_operations_controllers.owner_actions"
    ),
    "owner_menu": (
        "velvet_bot.presentation.telegram.routers.core_operations_controllers.owner_menu"
    ),
    "watermark": (
        "velvet_bot.presentation.telegram.routers.core_operations_controllers.watermark"
    ),
}


class P3CCoreOperationsControllersTests(unittest.TestCase):
    def test_retired_legacy_files_are_removed(self) -> None:
        for alias_name in RETIRED:
            with self.subTest(alias=alias_name):
                self.assertFalse((HANDLERS / f"{alias_name}.py").exists())

    def test_canonical_modules_own_core_handlers(self) -> None:
        root = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers"
        )
        error_center = (root / "error_center.py").read_text(encoding="utf-8")
        owner_actions = (root / "owner_actions.py").read_text(encoding="utf-8")
        owner_menu = (root / "owner_menu.py").read_text(encoding="utf-8")
        watermark = (root / "watermark.py").read_text(encoding="utf-8")

        self.assertIn('Command("test_error_alert")', error_center)
        self.assertIn('F.data.startswith("err:ack:")', error_center)
        self.assertIn("OwnerActionCallback.filter()", owner_actions)
        self.assertIn("class OwnerActionReplyFilter", owner_actions)
        self.assertIn('Command("menu", "admin")', owner_menu)
        self.assertIn("OwnerMenuCallback.filter()", owner_menu)
        self.assertIn("router.include_router(watermark_router)", owner_menu)
        self.assertIn("router = Router(name=__name__)", watermark)
        self.assertIn('Command("watermark")', watermark)

    def test_core_bundle_uses_canonical_controllers_in_original_order(self) -> None:
        path = ROOT / "velvet_bot/presentation/telegram/routers/core_operations.py"
        source = path.read_text(encoding="utf-8")
        for alias_name, canonical_name in RETIRED.items():
            if alias_name == "watermark":
                continue
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
