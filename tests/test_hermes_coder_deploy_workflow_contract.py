from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-hermes-coders.yml"
RELEASE = ROOT / "deploy" / "hermes-coders" / "release.sh"
INSTALL = ROOT / "deploy" / "hermes-coders" / "install.sh"
ROOT_RUNNER = ROOT / "deploy" / "hermes-coders" / "release-root-runner.sh"
RUNNER_INSTALLER = (
    ROOT / "deploy" / "hermes-coders" / "install-release-root-runner.sh"
)
SANDBOX_PREFLIGHT = ROOT / "deploy" / "hermes-coders" / "sandbox_preflight.py"


class HermesCoderDeployWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.release = RELEASE.read_text(encoding="utf-8")
        cls.install = INSTALL.read_text(encoding="utf-8")
        cls.root_runner = ROOT_RUNNER.read_text(encoding="utf-8")
        cls.runner_installer = RUNNER_INSTALLER.read_text(encoding="utf-8")
        cls.sandbox_preflight = SANDBOX_PREFLIGHT.read_text(encoding="utf-8")

    def test_release_requires_exact_current_main_ref(self) -> None:
        self.assertIn('release/hermes-coders-*', self.workflow)
        self.assertIn('release/hermes-coders-${source_commit}', self.workflow)
        self.assertIn('git fetch --no-tags origin main', self.workflow)
        self.assertIn(
            'Hermes release must point to the current main commit',
            self.workflow,
        )
        self.assertIn(
            'refs/heads/main:refs/remotes/origin/main',
            self.root_runner,
        )
        self.assertIn(
            'target is no longer current main',
            self.root_runner,
        )

    def test_release_uses_production_environment_and_root_lock_dir(self) -> None:
        self.assertIn('environment: production', self.workflow)
        self.assertIn('timeout-minutes: 30', self.workflow)
        self.assertIn('velvet-hermes-coder-production', self.workflow)
        self.assertIn('/run/lock/hermes-coders', self.root_runner)
        self.assertIn('TMPDIR="$LOCK_DIR"', self.root_runner)
        self.assertIn('velvet-hermes-coder-release.lock', self.release)
        self.assertNotIn('TMPDIR=/tmp', self.root_runner)

    def test_root_runner_stages_exact_detached_worktree(self) -> None:
        self.assertIn(
            'release_runner=/usr/local/sbin/hermes-coders-release',
            self.workflow,
        )
        self.assertIn(
            'sudo -n "$release_runner" "$target_sha"',
            self.workflow,
        )
        self.assertNotIn('sudo -n env', self.workflow)
        self.assertNotIn('git worktree add --detach', self.workflow)
        self.assertIn(
            'root_git -C "$MIRROR_REPO" worktree add --detach',
            self.root_runner,
        )
        self.assertIn(
            'HERMES_RELEASE_ROOT="$release_dir"',
            self.root_runner,
        )
        self.assertIn(
            '"$release_script" "$TARGET_SHA" "$APP_DIR"',
            self.root_runner,
        )

    def test_root_runner_does_not_execute_user_writable_release_code(self) -> None:
        for marker in (
            'MIRROR_ROOT=/var/lib/hermes-coders-release',
            'REPOSITORY_URL=https://github.com/Stellmaria/Velvet.git',
            'assert_root_tree "$MIRROR_ROOT" "release mirror"',
            'assert_root_tree "$release_dir" "release worktree"',
            '! -user root -o ! -group root -o -perm /022',
            'fixed directory must not be a symlink',
            'root_git -C "$release_dir" diff --quiet',
            'ls-files --others --exclude-standard',
            '/usr/bin/env -i',
            'GIT_CONFIG_NOSYSTEM=1',
        ):
            self.assertIn(marker, self.root_runner)
        self.assertNotIn('git -C "$APP_DIR" fetch', self.root_runner)
        self.assertNotIn('HERMES_RELEASE_ROOT="${', self.workflow)

    def test_sudoers_installer_is_bounded_to_root_owned_runner(self) -> None:
        for marker in (
            'APP_USER=velvet',
            'install -o root -g root -m 0755 "$SOURCE" "$RUNNER_TARGET"',
            'Cmnd_Alias HERMES_CODERS_RELEASE = $RUNNER_TARGET',
            'NOPASSWD: HERMES_CODERS_RELEASE',
            'chmod 0440 "$sudoers_tmp"',
            'visudo -cf "$sudoers_tmp"',
            'visudo -cf "$SUDOERS_TARGET"',
        ):
            self.assertIn(marker, self.runner_installer)
        self.assertNotIn('HERMES_CODERS_APP_USER', self.runner_installer)
        self.assertNotIn('NOPASSWD: ALL', self.runner_installer)
        self.assertNotIn('SETENV', self.runner_installer)
        self.assertNotIn('/bin/bash', self.runner_installer)

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
        override = self.release.index(
            'rollback_compose+=( -f "$OVERRIDE_FILE" )'
        )
        rollback = self.release.index('rollback()')
        activation = self.release.rindex('"$SOURCE_DIR/install.sh"')
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
            '.RestartCount',
            '{{json .HostConfig.Init}}',
            'apparmor=hermes-codex-runner',
        ):
            self.assertIn(marker, self.release)
        self.assertIn('sandbox_preflight.py', self.install)
        self.assertIn('client.probe(project)', self.sandbox_preflight)
        self.assertIn('for project in _PROJECTS', self.sandbox_preflight)

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
            'docker compose down',
        ):
            self.assertNotIn(forbidden, self.release + self.root_runner)


if __name__ == "__main__":
    unittest.main()
