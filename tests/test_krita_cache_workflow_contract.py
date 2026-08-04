from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CACHE_WORKFLOW = ROOT / ".github/workflows/krita-cache-warm.yml"
DOCKER_WORKFLOW = ROOT / ".github/workflows/docker-build.yml"
DOCKERFILE = ROOT / "Dockerfile.krita-server"


class KritaCacheWorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cache_workflow = CACHE_WORKFLOW.read_text(encoding="utf-8")
        self.docker_workflow = DOCKER_WORKFLOW.read_text(encoding="utf-8")
        self.dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    def test_warmer_runs_only_from_trusted_default_branch_contexts(self) -> None:
        self.assertIn("workflow_dispatch:", self.cache_workflow)
        self.assertIn("schedule:", self.cache_workflow)
        self.assertIn('cron: "17 4 * * 1,4"', self.cache_workflow)
        self.assertIn("branches:\n      - main", self.cache_workflow)
        self.assertNotIn("pull_request:", self.cache_workflow)

    def test_warmer_has_read_only_repository_permissions(self) -> None:
        self.assertIn("permissions:\n  contents: read", self.cache_workflow)
        self.assertNotIn("packages: write", self.cache_workflow)
        self.assertNotIn("--push", self.cache_workflow)
        self.assertNotIn("ghcr.io", self.cache_workflow)

    def test_warmer_and_pr_build_share_the_default_cache_scope(self) -> None:
        cache_from = "--cache-from type=gha,scope=velvet-krita"
        cache_to = "--cache-to type=gha,mode=max,scope=velvet-krita"
        self.assertIn(cache_from, self.cache_workflow)
        self.assertIn(cache_to, self.cache_workflow)
        self.assertIn(cache_from, self.docker_workflow)
        self.assertIn(cache_to, self.docker_workflow)

    def test_warmer_is_bounded_and_cancels_stale_runs(self) -> None:
        self.assertIn("timeout-minutes: 35", self.cache_workflow)
        self.assertIn("cancel-in-progress: true", self.cache_workflow)
        self.assertIn("group: krita-cache-warm-${{ github.ref }}", self.cache_workflow)

    def test_heavy_package_layer_precedes_repository_copies(self) -> None:
        self.assertLess(
            self.dockerfile.index("apt-get install"),
            self.dockerfile.index("COPY "),
        )

    def test_warmer_self_triggers_after_merge(self) -> None:
        self.assertIn(
            '- ".github/workflows/krita-cache-warm.yml"',
            self.cache_workflow,
        )

    def test_warmed_image_is_verified_without_starting_the_service(self) -> None:
        self.assertIn("docker image inspect velvet-krita-server:cache-warm", self.cache_workflow)
        self.assertIn("command -v krita", self.cache_workflow)
        self.assertIn("command -v python3", self.cache_workflow)


if __name__ == "__main__":
    unittest.main()
