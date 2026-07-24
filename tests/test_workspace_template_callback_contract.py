from __future__ import annotations

import unittest
from pathlib import Path

from velvet_bot.core.access import (
    WORKSPACE_MEMBER_CALLBACK_PREFIXES,
    is_workspace_member_callback_data,
)

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceTemplateCallbackContractTests(unittest.TestCase):
    def test_template_callback_is_a_canonical_workspace_member_callback(self) -> None:
        self.assertIn("wmtpl:", WORKSPACE_MEMBER_CALLBACK_PREFIXES)
        self.assertTrue(is_workspace_member_callback_data("wmtpl:show:9:"))
        self.assertTrue(is_workspace_member_callback_data("wmtpl:save:9:"))

    def test_unrelated_callback_is_not_classified_as_workspace_member(self) -> None:
        self.assertFalse(is_workspace_member_callback_data("unknown:show:9"))
        self.assertFalse(is_workspace_member_callback_data(None))

    def test_workspace_installer_does_not_patch_access_classifier(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
            "workspace_product_experience.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("access_middleware.is_workspace_member_callback_data =", source)
        self.assertNotIn("def _workspace_callback_with_template", source)
        self.assertNotIn("_ORIGINAL_MEMBER_CALLBACK_CHECK", source)
        self.assertNotIn("middleware import access as access_middleware", source)


if __name__ == "__main__":
    unittest.main()
