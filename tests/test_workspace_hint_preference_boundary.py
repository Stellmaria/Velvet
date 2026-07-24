from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.workspaces.product_service import WorkspaceProductService

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceHintPreferenceServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.product = SimpleNamespace(
            get_button_hints=AsyncMock(return_value=False),
            toggle_button_hints=AsyncMock(return_value=True),
        )
        self.service = WorkspaceProductService(
            product_repository=self.product,
            workspace_repository=SimpleNamespace(),
        )

    async def test_get_button_hints_delegates_to_product_repository(self) -> None:
        result = await self.service.get_button_hints(9)

        self.assertFalse(result)
        self.product.get_button_hints.assert_awaited_once_with(9)

    async def test_toggle_button_hints_delegates_to_product_repository(self) -> None:
        result = await self.service.toggle_button_hints(9)

        self.assertTrue(result)
        self.product.toggle_button_hints.assert_awaited_once_with(9)

    async def test_toggle_button_hints_rejects_missing_settings(self) -> None:
        self.product.toggle_button_hints.return_value = None

        with self.assertRaisesRegex(ValueError, "Настройки пространства не найдены"):
            await self.service.toggle_button_hints(9)


class WorkspaceHintPreferenceControllerBoundaryTests(unittest.TestCase):
    def test_workspace_presentation_has_no_hint_sql_or_private_repository_access(self) -> None:
        controller_source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
            "workspace_product_experience.py"
        ).read_text(encoding="utf-8")
        home_source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/"
            "workspace_owner_controls.py"
        ).read_text(encoding="utf-8")

        for source in (controller_source, home_source):
            self.assertNotIn("SELECT show_button_hints", source)
            self.assertNotIn("UPDATE workspace_settings", source)
            self.assertNotIn("workspace_product_service._workspaces", source)
            self.assertNotIn("_database_from_product_service", source)
        self.assertIn(
            "workspace_product_service.get_button_hints",
            home_source,
        )
        self.assertIn(
            "workspace_product_service.toggle_button_hints",
            controller_source,
        )


if __name__ == "__main__":
    unittest.main()
