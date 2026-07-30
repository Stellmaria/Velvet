from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github/workflows"
WORKFLOW = WORKFLOW_DIR / "branch-maintenance.yml"
RUNBOOK = ROOT / "docs/runbooks/branch_maintenance.md"


class BranchMaintenanceWorkflowTests(unittest.TestCase):
    def test_workflow_is_manual_sha_guarded_and_non_protected(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", source)
        self.assertIn("expected_target_sha:", source)
        self.assertIn("source_commit_sha:", source)
        self.assertIn("type: choice", source)
        self.assertIn("- cherry-pick", source)
        self.assertIn("contents: write", source)
        self.assertIn("cancel-in-progress: false", source)
        self.assertIn("timeout-minutes: 45", source)
        self.assertIn("agent|feature|fix|chore|maintenance", source)
        self.assertIn('"main"', source)
        self.assertIn('"master"', source)
        self.assertIn("Target moved:", source)
        self.assertIn("Target moved during validation:", source)
        self.assertIn("40-character commit SHA", source)
        self.assertIn("single-parent commit", source)

    def test_workflow_plans_tests_and_pushes_without_force(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('git cherry-pick --no-commit "$source"', source)
        self.assertIn("git diff --cached --check", source)
        self.assertIn("git diff --cached --quiet", source)
        self.assertIn("git diff --cached --name-status", source)
        self.assertIn("git diff --cached --stat", source)
        self.assertIn("maintenance-changed-files.txt", source)
        self.assertIn("maintenance-diff-stat.txt", source)
        self.assertIn("python -m unittest discover -s tests -v", source)
        self.assertIn('git push origin "HEAD:refs/heads/${target}"', source)
        self.assertIn("git merge-base --is-ancestor", source)
        self.assertIn("equivalent patch", source)
        self.assertNotIn("git push --force", source)
        self.assertNotIn("--force-with-lease", source)
        self.assertNotIn("git merge origin/main", source)
        self.assertNotIn("git checkout --theirs", source)
        self.assertNotIn("git checkout --ours", source)

    def test_contents_write_workflows_are_small_and_allowlisted(self) -> None:
        write_workflows = {
            path.name
            for path in WORKFLOW_DIR.iterdir()
            if path.suffix in {".yml", ".yaml"}
            and "contents: write" in path.read_text(encoding="utf-8")
        }

        self.assertEqual(
            {
                "branch-maintenance.yml",
                "release.yml",
                "tag-stable-release.yml",
            },
            write_workflows,
        )
        self.assertFalse(
            (WORKFLOW_DIR / "apply-shared-helper-migration.yml").exists()
        )

    def test_runbook_separates_pr_and_maintenance_use_cases(self) -> None:
        source = RUNBOOK.read_text(encoding="utf-8")

        self.assertIn("не заменяет обычный pull request", source)
        self.assertIn("точный текущий SHA", source)
        self.assertIn("не разрешает конфликты автоматически", source)
        self.assertIn("не создаёт duplicate commit", source)
        self.assertIn("direct mutation `main`", source)
        self.assertIn("force-push", source)
        self.assertIn("Audit trail", source)


if __name__ == "__main__":
    unittest.main()
