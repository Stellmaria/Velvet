from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-hermes-coders.yml"
RELEASE = ROOT / "deploy" / "hermes-coders" / "release.sh"


class HermesCoderDeployWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.release = RELEASE.read_text(encoding="utf-8")

    def test_release_requires_exact_current_main_ref(self) -> None:
        self.assertIn('release/hermes-coders-*', self.workflow)
        self.assertIn('release/hermes-coders-${source_commit}', self.workflow)
        self.assertIn('git fetch --no-tags origin main', self.workflow)
        self.assertIn('Hermes release must point to the current main commit', self.workflow)
        self.assertIn('Target is no longer current main', self.workflow + self.release)

    def test_release_uses_production_environment_and_bounded_lock(self) -> None:
        self.assertIn('environment: production', self.workflow)
        self.assertIn('timeout-minutes: 30', self.workflow)
        self.assertIn('velvet-hermes-coder-production', self.workflow)
        self.assertIn('velvet-hermes-coder-release.lock', self.release)

    def test_workflow_creates_exact_detached_worktree_and_runs_versioned_script(self) -> None:
        self.assertIn('git worktree add --detach', self.workflow)
        self.assertIn('release_script="$release_dir/deploy/hermes-coders/release.sh"', self.workflow)
        self.assertIn('HERMES_RELEASE_ROOT="$release_dir"', self.workflow)
        self.assertIn('sudo -n env', self.workflow)
        self.assertNotIn('git reset --hard', self.workflow + self.release)
        self.assertNotIn('git clean', self.workflow + self.release)
        self.assertNotIn('docker compose down', self.workflow + self.release)

    def test_canonical_activation_uses_installer_and_release_symlink(self) -> None:
        self.assertIn('"$SOURCE_DIR/install.sh"', self.release)
        self.assertIn('current-hermes-coders', self.release)
        self.assertIn('readlink -f "$CURRENT_LINK"', self.release)
        self.assertIn('hermes-sandbox-launcher', self.release)
        self.assertIn('apparmor=hermes-codex-runner', self.release)
        self.assertNotIn('compose.bwrap.override.yaml', self.workflow)

    def test_compatibility_override_exists_only_in_rollback(self) -> None:
        marker = '# Compatibility override is permitted only in rollback'
        self.assertIn(marker, self.release)
        override = self.release.index('rollback_compose+=( -f "$OVERRIDE_FILE" )')
        rollback = self.release.index('rollback()')
        activation = self.release.index('"$SOURCE_DIR/install.sh"')
        self.assertGreater(override, rollback)
        self.assertLess(override, activation)
        canonical_slice = self.release[activation:]
        self.assertNotIn('OVERRIDE_FILE', canonical_slice)

    def test_release_backs_up_root_artifacts_and_image_identity(self) -> None:
        for marker in (
            '/usr/local/lib/hermes-sandbox-launcher',
            '/etc/systemd/system/hermes-sandbox-launcher.socket',
            '/etc/systemd/system/hermes-coders.service',
            '/etc/apparmor.d/hermes-codex-runner',
            'PREVIOUS_VELVET_IMAGE',
            'PREVIOUS_MAX_IMAGE',
            'docker tag',
        ):
            self.assertIn(marker, self.release)

    def test_release_verifies_security_source_and_zero_zombies(self) -> None:
        for marker in (
            '/app/codex_launcher_runner.py',
            'actual_runner_sha',
            'container_zombies',
            'host_zombies',
            'client.probe',
            '.RestartCount',
            '{{json .HostConfig.Init}}',
            'apparmor=hermes-codex-runner',
        ):
            self.assertIn(marker, self.release)

    def test_release_has_fail_closed_rollback_without_persistent_deletion(self) -> None:
        self.assertIn('rollback()', self.release)
        self.assertIn('restoring previous runtime', self.release)
        self.assertIn('trap rollback ERR INT TERM', self.release)
        self.assertIn('trap - ERR INT TERM', self.release)
        for forbidden in (
            'rm -rf -- "$ROOT/codex"',
            'rm -rf -- "$ROOT/codex-runs"',
            'rm -rf -- "$ROOT/workspaces"',
            'docker volume rm',
        ):
            self.assertNotIn(forbidden, self.release)


if __name__ == "__main__":
    unittest.main()
