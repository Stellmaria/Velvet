from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-hermes-coders.yml"


class HermesCoderDeployWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_release_requires_exact_current_main_ref(self) -> None:
        self.assertIn('release/hermes-coders-*', self.source)
        self.assertIn('release/hermes-coders-${source_commit}', self.source)
        self.assertIn('git fetch --no-tags origin main', self.source)
        self.assertIn('Hermes release must point to the current main commit', self.source)
        self.assertIn('Target is no longer current main', self.source)

    def test_release_uses_production_environment_and_bounded_lock(self) -> None:
        self.assertIn('environment: production', self.source)
        self.assertIn('timeout-minutes: 20', self.source)
        self.assertIn('velvet-hermes-coder-production', self.source)
        self.assertIn('velvet-hermes-coder-release.lock', self.source)

    def test_release_uses_detached_worktree_without_touching_checkout(self) -> None:
        self.assertIn('git worktree add --detach', self.source)
        self.assertNotIn('git reset --hard', self.source)
        self.assertNotIn('git clean', self.source)
        self.assertNotIn('docker compose down', self.source)

    def test_release_recreates_only_coder_services(self) -> None:
        self.assertIn('--no-deps --no-build --force-recreate', self.source)
        self.assertIn('hermes-coder-velvet hermes-coder-max', self.source)
        self.assertNotIn('deploy/server/deploy.sh', self.source)
        self.assertNotIn('migrations/', self.source)
        self.assertNotIn('postgres supervisor-proxy bot', self.source)

    def test_release_preserves_runtime_sandbox_and_image(self) -> None:
        self.assertIn('compose.security.yaml', self.source)
        self.assertIn('compose.bwrap.override.yaml', self.source)
        self.assertIn("previous_velvet_image", self.source)
        self.assertIn("previous_max_image", self.source)
        self.assertIn("{{json .HostConfig.Init}}", self.source)
        self.assertIn(".RestartCount", self.source)

    def test_release_verifies_exact_mounted_source_and_zero_zombies(self) -> None:
        self.assertIn('/app/codex_tier_runner.py', self.source)
        self.assertIn('mounted_source', self.source)
        self.assertIn('actual_sha', self.source)
        self.assertIn('container_zombies', self.source)
        self.assertIn('zombies_after', self.source)

    def test_release_has_fail_closed_rollback(self) -> None:
        self.assertIn('rollback()', self.source)
        self.assertIn('restoring containers from $previous_compose_dir', self.source)
        self.assertIn('trap rollback ERR INT TERM', self.source)
        self.assertIn('trap - ERR INT TERM', self.source)


if __name__ == "__main__":
    unittest.main()
