from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/docker-build.yml"


class DockerBuildWorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_stale_runs_are_cancelled_per_pull_request_or_ref(self) -> None:
        self.assertIn("concurrency:", self.workflow)
        self.assertIn(
            "group: docker-build-${{ github.event.pull_request.number || github.ref }}",
            self.workflow,
        )
        self.assertIn("cancel-in-progress: true", self.workflow)

    def test_build_has_a_bounded_timeout(self) -> None:
        self.assertIn("timeout-minutes: 40", self.workflow)

    def test_workflow_changes_trigger_the_docker_build(self) -> None:
        self.assertGreaterEqual(
            self.workflow.count('- ".github/workflows/docker-build.yml"'),
            2,
        )


if __name__ == "__main__":
    unittest.main()
