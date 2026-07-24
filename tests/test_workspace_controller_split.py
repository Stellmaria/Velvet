from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_command_filtering import (
    command_name,
)

ROOT = Path(__file__).resolve().parents[1]
CONTROLLERS = (
    ROOT
    / "velvet_bot/presentation/telegram/routers/core_operations_controllers"
)


class WorkspaceCommandFilteringTests(unittest.TestCase):
    def test_command_name_accepts_bot_suffix(self) -> None:
        message = SimpleNamespace(
            text="/archive@DominusVelvetBot extra",
            caption=None,
        )

        self.assertEqual("archive", command_name(message))

    def test_command_name_falls_back_to_caption(self) -> None:
        message = SimpleNamespace(
            text=None,
            caption="/watermark@DominusVelvetBot",
        )

        self.assertEqual("watermark", command_name(message))


class WorkspaceControllerSplitTests(unittest.TestCase):
    def test_product_experience_only_keeps_home_preference_flow(self) -> None:
        source = (
            CONTROLLERS / "workspace_product_experience.py"
        ).read_text(encoding="utf-8")

        self.assertIn("handle_workspace_help_toggle", source)
        for forbidden in (
            "PersonalArchiveCommandFilter",
            "WatermarkCommandFilter",
            "WatermarkCallback",
            "core_watermark",
            "_DRAFT_ACTIONS",
        ):
            self.assertNotIn(forbidden, source)

    def test_archive_controller_owns_personal_archive_command(self) -> None:
        source = (
            CONTROLLERS / "workspace_archive_controller.py"
        ).read_text(encoding="utf-8")

        self.assertIn("class PersonalArchiveCommandFilter", source)
        self.assertIn("handle_personal_archive_command", source)
        self.assertNotIn("WatermarkCallback", source)

    def test_watermark_controller_owns_draft_flow(self) -> None:
        source = (
            CONTROLLERS / "workspace_watermark_draft_controller.py"
        ).read_text(encoding="utf-8")

        self.assertIn("class WatermarkCommandFilter", source)
        self.assertIn("handle_watermark_draft_callback", source)
        self.assertIn("handle_watermark_draft_color", source)
        self.assertNotIn("_load_archive_characters", source)

    def test_owner_menu_composes_specific_routers_before_legacy_watermark(self) -> None:
        source = (CONTROLLERS / "owner_menu.py").read_text(encoding="utf-8")

        archive = source.index("router.include_router(workspace_archive_router)")
        product = source.index(
            "router.include_router(workspace_product_experience_router)"
        )
        draft = source.index(
            "router.include_router(workspace_watermark_draft_router)"
        )
        legacy = source.index("router.include_router(watermark_router)")

        self.assertLess(archive, product)
        self.assertLess(product, draft)
        self.assertLess(draft, legacy)


if __name__ == "__main__":
    unittest.main()
