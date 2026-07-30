from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceQwenComparisonFlowContractTests(unittest.TestCase):
    def test_reference_button_starts_a_workspace_pinned_result_session(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_reference_library.py"
        ).read_text(encoding="utf-8")

        self.assertIn("WorkspaceReferenceComparisonForm.waiting_result", source)
        self.assertIn("require_qwen=True", source)
        self.assertIn("reference_id=page.reference.id", source)
        self.assertIn("workspace_id=personal_reference_context.workspace_id", source)

    def test_result_handler_rechecks_the_pinned_reference_inside_workspace(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_reference_library.py"
        ).read_text(encoding="utf-8")

        self.assertIn("page.reference.id != reference_id", source)
        self.assertIn("workspace_id=personal_reference_context.workspace_id", source)
        self.assertIn("_compare_workspace_reference_result(", source)

    def test_legacy_command_uses_the_same_comparison_operation(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_reference_library.py"
        ).read_text(encoding="utf-8")

        command_index = source.index('Command("compare_ref", "compare_reference")')
        helper_index = source.index("async def _compare_workspace_reference_result")
        self.assertLess(command_index, helper_index)
        self.assertIn("reference_total=len(references)", source[command_index:helper_index])


if __name__ == "__main__":
    unittest.main()
