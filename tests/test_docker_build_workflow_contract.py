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

    def test_build_jobs_have_bounded_timeouts(self) -> None:
        self.assertGreaterEqual(self.workflow.count("timeout-minutes: 40"), 5)
        self.assertIn("timeout-minutes: 2", self.workflow)

    def test_workflow_changes_trigger_the_docker_build(self) -> None:
        self.assertGreaterEqual(
            self.workflow.count('- ".github/workflows/docker-build.yml"'),
            2,
        )

    def test_heavy_docker_surfaces_run_as_parallel_jobs(self) -> None:
        for job in (
            "build-velvet",
            "build-supervisor",
            "build-vision",
            "build-krita",
            "build-hermes",
        ):
            self.assertIn(f"  {job}:\n", self.workflow)
            self.assertIn("needs: changes", self.workflow)

        self.assertIn(
            "if: needs.changes.outputs.docker_velvet == 'true'",
            self.workflow,
        )
        self.assertIn(
            "if: needs.changes.outputs.docker_krita == 'true'",
            self.workflow,
        )
        self.assertIn(
            "if: needs.changes.outputs.docker_hermes == 'true'",
            self.workflow,
        )

    def test_hermes_shared_images_are_built_once_with_gha_cache(self) -> None:
        self.assertIn(
            "--file deploy/hermes-coders/Dockerfile.coder",
            self.workflow,
        )
        self.assertIn(
            "--cache-from type=gha,scope=velvet-hermes-coder",
            self.workflow,
        )
        self.assertIn(
            "--cache-to type=gha,mode=max,scope=velvet-hermes-coder,ignore-error=true",
            self.workflow,
        )
        for tag in (
            "velvet-hermes-chat-velvet:local",
            "velvet-codex-coder-velvet:local",
            "velvet-hermes-chat-max:local",
            "velvet-codex-coder-max:local",
        ):
            self.assertEqual(self.workflow.count(f"--tag {tag}"), 1)

        self.assertIn(
            "--file deploy/hermes-coders/Dockerfile.db-proxy",
            self.workflow,
        )
        self.assertIn(
            "--cache-from type=gha,scope=velvet-hermes-db-proxy",
            self.workflow,
        )
        for tag in (
            "velvet-hermes-db-proxy-velvet:local",
            "velvet-hermes-db-proxy-max:local",
        ):
            self.assertEqual(self.workflow.count(f"--tag {tag}"), 1)

        self.assertNotIn(
            "-f deploy/hermes-coders/compose.yaml \\\n              build",
            self.workflow,
        )

    def test_required_build_check_is_a_fail_closed_aggregator(self) -> None:
        self.assertIn("  build:\n    name: build\n    if: always()", self.workflow)
        for job in (
            "changes",
            "validate",
            "build-velvet",
            "build-supervisor",
            "build-vision",
            "build-krita",
            "build-hermes",
        ):
            self.assertIn(f"      - {job}\n", self.workflow)
        self.assertIn('test "$CHANGES_RESULT" = "success"', self.workflow)
        self.assertIn('test "$VALIDATE_RESULT" = "success"', self.workflow)
        self.assertIn(
            'test "$result" = "success" || test "$result" = "skipped"',
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
