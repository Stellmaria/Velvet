from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODERS = ROOT / "deploy/hermes-coders"
sys.path.insert(0, str(CODERS))

import codex_launcher_runner as launcher  # noqa: E402


class LauncherWorkspacePromptTests(unittest.TestCase):
    def test_controller_workspace_notice_is_translated_for_disposable_sandbox(self) -> None:
        controller_workspace = Path(
            "/opt/codex-runs/workspaces/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )
        controller_notice = (
            f"EFFECTIVE RUN WORKSPACE: {controller_workspace}\n"
            "This current working directory is the only task checkout. "
            "Do not access /workspace, /workspace-base, chat workspaces or sibling runs."
        )
        prompt = (
            f"{controller_notice}\n\nread-only instructions\n\n"
            f"{controller_notice}\n\ninspect README"
        )

        rewritten = launcher.sandbox_visible_prompt(prompt, controller_workspace)

        self.assertEqual(2, rewritten.count("EFFECTIVE RUN WORKSPACE: /workspace"))
        self.assertNotIn(f"EFFECTIVE RUN WORKSPACE: {controller_workspace}", rewritten)
        self.assertNotIn("Do not access /workspace,", rewritten)
        self.assertEqual(2, rewritten.count("Do not access /workspace-base"))

    def test_unrelated_user_text_is_not_rewritten(self) -> None:
        controller_workspace = Path(
            "/opt/codex-runs/workspaces/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        )
        prompt = f"User diagnostic mentions {controller_workspace} but has no injected notice."

        self.assertEqual(
            prompt,
            launcher.sandbox_visible_prompt(prompt, controller_workspace),
        )


if __name__ == "__main__":
    unittest.main()
