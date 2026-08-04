from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "report-hermes-coder-release.yml"


class HermesReleaseEvidenceWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_reporter_only_follows_completed_release_workflow(self) -> None:
        self.assertIn("workflow_run:", self.source)
        self.assertIn("- deploy Hermes coders", self.source)
        self.assertIn("- completed", self.source)
        self.assertNotIn("pull_request_target", self.source)

    def test_reporter_has_bounded_permissions(self) -> None:
        self.assertIn("actions: read", self.source)
        self.assertIn("contents: read", self.source)
        self.assertIn("issues: write", self.source)
        self.assertNotIn("contents: write", self.source)
        self.assertNotIn("actions: write", self.source)

    def test_reporter_validates_exact_release_ref_identity(self) -> None:
        self.assertIn('expected_prefix="release/hermes-coders-"', self.source)
        self.assertIn("Release branch SHA does not match workflow head", self.source)
        self.assertIn("^[0-9a-f]{40}$", self.source)

    def test_reporter_does_not_checkout_or_execute_release_code(self) -> None:
        self.assertNotIn("actions/checkout", self.source)
        self.assertNotIn("git checkout", self.source)
        self.assertNotIn("git reset", self.source)
        self.assertNotIn("ssh ", self.source)
        self.assertNotIn("docker ", self.source)

    def test_reporter_redacts_and_bounds_log_evidence(self) -> None:
        self.assertIn("gh run view", self.source)
        self.assertIn("tail -n 80", self.source)
        self.assertIn("<redacted>", self.source)
        self.assertIn("release-tail.log", self.source)

    def test_reporter_comments_fixed_issue_and_propagates_failure(self) -> None:
        self.assertIn("gh issue comment 592", self.source)
        self.assertIn("github.event.workflow_run.conclusion != 'success'", self.source)
        self.assertIn("Hermes coder release did not succeed", self.source)


if __name__ == "__main__":
    unittest.main()
