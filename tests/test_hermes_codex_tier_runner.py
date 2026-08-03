from __future__ import annotations

import importlib.util
import os
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
        workspace = root / "workspace"
        (workspace / ".git").mkdir(parents=True)
        self.env = patch.dict(
            os.environ,
            {
                "CODEX_RUNNER_API_KEY": "r" * 48,
                "CODEX_HOME": str(codex_home),
                "CODEX_WORKSPACE": str(workspace),
                "CODEX_RUN_ROOT": str(root / "runs"),
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

    def seed(self, run_id: str, mutation_policy: str) -> None:
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
        self.manager._run_baselines[run_id] = "baseline"
        self.manager._fingerprint = lambda: "changed"

    def test_successful_workspace_mutation_is_persisted(self) -> None:
        run_id = "a" * 32
        self.seed(run_id, "workspace_write")
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
        self.assertTrue(self.manager.store.read(run_id)["mutation_started"])
        parent_success.assert_called_once()

    def test_read_only_mutation_is_rejected_before_success(self) -> None:
        run_id = "b" * 32
        self.seed(run_id, "read_only")
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

    def test_capabilities_publish_safe_mutation_audit(self) -> None:
        audit = self.manager.capabilities()["routing"]["mutation_audit"]
        self.assertEqual(
            {"successful_runs": True, "read_only_fail_closed": True}, audit
        )


if __name__ == "__main__":
    unittest.main()
