from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


base = load_module("codex_runner", ROOT / "deploy/hermes-coders/codex_runner.py")
routed = load_module(
    "codex_routed_runner",
    ROOT / "deploy/hermes-coders/codex_routed_runner.py",
)
first = load_module(
    "codex_first_runner",
    ROOT / "deploy/hermes-coders/codex_first_runner.py",
)
safe = load_module(
    "codex_first_safe_runner",
    ROOT / "deploy/hermes-coders/codex_first_safe_runner.py",
)
provider = load_module(
    "codex_provider_chain_runner",
    ROOT / "deploy/hermes-coders/codex_provider_chain_runner.py",
)
tier = load_module(
    "codex_tier_runner_test_module",
    ROOT / "deploy/hermes-coders/codex_tier_runner.py",
)


class AuditedTierRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        codex_home = root / "codex"
        codex_home.mkdir()
        (codex_home / "AGENTS.md").write_text("agents\n", encoding="utf-8")
        (codex_home / "output.schema.json").write_text(
            '{"type":"object"}\n', encoding="utf-8"
        )
        (codex_home / "auth.json").write_text("{}\n", encoding="utf-8")

        self.remote = root / "origin.git"
        self.base_workspace = root / "workspace-base"
        subprocess.run(
            ["git", "init", "--bare", str(self.remote)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "init", "-b", "main", str(self.base_workspace)],
            check=True,
            capture_output=True,
        )
        self.git(self.base_workspace, "config", "user.name", "Test Coder")
        self.git(self.base_workspace, "config", "user.email", "coder@example.invalid")
        (self.base_workspace / "README.md").write_text("# test\n", encoding="utf-8")
        self.git(self.base_workspace, "add", "README.md")
        self.git(self.base_workspace, "commit", "-m", "initial")
        self.git(self.base_workspace, "remote", "add", "origin", str(self.remote))
        self.git(self.base_workspace, "push", "-u", "origin", "main")
        subprocess.run(
            ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
            cwd=self.remote,
            check=True,
            capture_output=True,
        )
        self.git(self.base_workspace, "remote", "set-head", "origin", "main")

        self.env = patch.dict(
            os.environ,
            {
                "CODEX_RUNNER_API_KEY": "r" * 48,
                "CODEX_HOME": str(codex_home),
                "CODEX_WORKSPACE": str(self.base_workspace),
                "CODEX_WORKSPACE_BASE": str(self.base_workspace),
                "CODEX_RUN_ROOT": str(root / "runs"),
                "CODEX_ISOLATED_WORKSPACE_ROOT": str(root / "runs" / "workspaces"),
                "CODEX_ALLOWED_MODELS": (
                    "gpt-5.6-luna,gpt-5.6-terra,gpt-5.6-sol"
                ),
                "CODEX_DEFAULT_MODEL": "gpt-5.6-terra",
                "CODEX_PROVIDER_FALLBACK_ENABLED": "false",
            },
            clear=False,
        )
        self.env.start()
        self.manager = tier.AuditedTierProviderManager()

    def tearDown(self) -> None:
        self.env.stop()
        self.temp.cleanup()

    @staticmethod
    def git(cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def seed(self, run_id: str, mutation_policy: str, workspace: Path) -> None:
        self.manager.store.write(
            {
                "run_id": run_id,
                "status": "running",
                "mutation_policy": mutation_policy,
                "requested_tier": "standard",
                "attempted_models": [],
                "attempted_routes": [],
                "mutation_started": False,
            }
        )
        self.manager.workspace = workspace
        self.manager._run_baselines[run_id] = self.manager._snapshot(workspace)
        self.manager._base_baselines[run_id] = self.manager._snapshot(
            self.base_workspace
        )

    def prepare(self, run_id: str) -> Path:
        workspace, source_ref = self.manager._prepare_workspace(run_id)
        self.assertEqual("origin/main", source_ref)
        self.assertNotEqual(self.base_workspace, workspace)
        self.assertTrue(workspace.is_dir())
        return workspace

    def test_prepare_workspace_uses_disposable_clone_not_git_worktree(self) -> None:
        run_id = "a" * 32
        workspace = self.prepare(run_id)
        try:
            self.assertEqual(
                self.git(self.base_workspace, "rev-parse", "HEAD").strip(),
                self.git(workspace, "rev-parse", "HEAD").strip(),
            )
            self.assertEqual(
                str(self.remote),
                self.git(workspace, "remote", "get-url", "origin").strip(),
            )
            self.assertFalse((self.base_workspace / ".git" / "worktrees").exists())
        finally:
            self.manager._cleanup_workspace(workspace)

    def test_clean_commit_is_still_recorded_as_mutation(self) -> None:
        run_id = "b" * 32
        workspace = self.prepare(run_id)
        self.seed(run_id, "workspace_write", workspace)
        self.git(workspace, "config", "user.name", "Test Coder")
        self.git(workspace, "config", "user.email", "coder@example.invalid")
        self.git(workspace, "switch", "-c", "agent/test-clean-commit")
        (workspace / "change.txt").write_text("changed\n", encoding="utf-8")
        self.git(workspace, "add", "change.txt")
        self.git(workspace, "commit", "-m", "change")
        self.assertEqual("", self.git(workspace, "status", "--porcelain").strip())

        with patch.object(
            tier.ProviderChainManager,
            "_success",
            autospec=True,
        ) as parent_success:
            self.manager._success(
                run_id,
                "gpt-5.6-terra",
                ["gpt-5.6-terra"],
                ["codex_subscription:gpt-5.6-terra"],
                "codex_subscription",
                None,
                "{}",
            )
        record = self.manager.store.read(run_id)
        self.assertTrue(record["mutation_started"])
        self.assertTrue(record["head_changed"])
        self.assertTrue(record["branch_changed"])
        self.assertTrue(record["refs_changed"])
        self.assertFalse(record["working_tree_changed"])
        parent_success.assert_called_once()
        self.manager._cleanup_workspace(workspace)

    def test_read_only_commit_is_rejected_even_when_status_is_clean(self) -> None:
        run_id = "c" * 32
        workspace = self.prepare(run_id)
        self.seed(run_id, "read_only", workspace)
        self.git(workspace, "config", "user.name", "Test Coder")
        self.git(workspace, "config", "user.email", "coder@example.invalid")
        (workspace / "change.txt").write_text("changed\n", encoding="utf-8")
        self.git(workspace, "add", "change.txt")
        self.git(workspace, "commit", "-m", "change")

        with patch.object(
            tier.ProviderChainManager,
            "_success",
            autospec=True,
        ) as parent_success:
            self.manager._success(
                run_id,
                "gpt-5.6-luna",
                ["gpt-5.6-luna"],
                ["codex_subscription:gpt-5.6-luna"],
                "codex_subscription",
                None,
                "{}",
            )
        record = self.manager.store.read(run_id)
        self.assertEqual("failed", record["status"])
        self.assertTrue(record["mutation_started"])
        self.assertEqual("read_only_mutation_blocked", record["last_event"]["type"])
        parent_success.assert_not_called()
        self.manager._cleanup_workspace(workspace)

    def test_base_checkout_change_is_fail_closed(self) -> None:
        run_id = "d" * 32
        workspace = self.prepare(run_id)
        self.seed(run_id, "read_only", workspace)
        (self.base_workspace / "base-change.txt").write_text("bad\n", encoding="utf-8")

        with patch.object(
            tier.ProviderChainManager,
            "_success",
            autospec=True,
        ) as parent_success:
            self.manager._success(
                run_id,
                "gpt-5.6-luna",
                ["gpt-5.6-luna"],
                ["codex_subscription:gpt-5.6-luna"],
                "codex_subscription",
                None,
                "{}",
            )
        record = self.manager.store.read(run_id)
        self.assertEqual("failed", record["status"])
        self.assertTrue(record["base_workspace_changed"])
        parent_success.assert_not_called()
        self.manager._cleanup_workspace(workspace)

    def test_execute_injects_effective_workspace_and_cleans_only_run_clone(self) -> None:
        run_id = "e" * 32
        self.manager.store.write(
            {
                "run_id": run_id,
                "status": "queued",
                "mutation_policy": "read_only",
                "requested_tier": "small",
                "task_type": "read_only",
            }
        )
        with patch.object(
            tier.ProviderChainManager,
            "_execute",
            autospec=True,
        ) as parent_execute:
            self.manager._execute(
                run_id,
                "inspect README",
                "read only",
                "gpt-5.6-luna",
            )
        args = parent_execute.call_args.args
        effective = self.manager.store.read(run_id)["workspace_path"]
        self.assertIn(f"EFFECTIVE RUN WORKSPACE: {effective}", args[2])
        self.assertIn("Do not access /workspace", args[2])
        self.assertFalse(Path(effective).exists())
        self.assertTrue(self.base_workspace.exists())

    def test_capabilities_publish_workspace_and_mutation_guards(self) -> None:
        routing = self.manager.capabilities()["routing"]
        self.assertEqual(
            {
                "per_run_clone": True,
                "base_checkout_read_only": True,
                "legacy_workspace_path": False,
            },
            routing["workspace_isolation"],
        )
        self.assertEqual(
            {
                "successful_runs": True,
                "head_and_refs": True,
                "working_tree": True,
                "base_checkout": True,
                "read_only_fail_closed": True,
            },
            routing["mutation_audit"],
        )


if __name__ == "__main__":
    unittest.main()
