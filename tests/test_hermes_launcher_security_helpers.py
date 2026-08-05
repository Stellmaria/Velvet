from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
TOKEN_MODULE = ROOT / "deploy/hermes-coders/ensure_launcher_tokens.py"
IDLE_MODULE = ROOT / "deploy/hermes-coders/ensure_idle.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class LauncherTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module("launcher_token_helper_test", TOKEN_MODULE)
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.velvet = root / "velvet.env"
        self.maximum = root / "max.env"
        self.secrets = root / "launcher-secrets.env"
        self.velvet.write_text("GH_TOKEN=velvet\n", encoding="utf-8")
        self.maximum.write_text("GH_TOKEN=max\n", encoding="utf-8")
        self.velvet.chmod(0o600)
        self.maximum.chmod(0o600)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_distinct_tokens_are_generated_without_rewriting_other_values(self) -> None:
        velvet = self.module.ensure_project_token(self.velvet)
        maximum = self.module.ensure_project_token(self.maximum)
        self.assertNotEqual(velvet, maximum)
        self.assertIn("GH_TOKEN=velvet", self.velvet.read_text(encoding="utf-8"))
        self.assertIn("GH_TOKEN=max", self.maximum.read_text(encoding="utf-8"))
        self.assertEqual(0o600, stat.S_IMODE(self.velvet.stat().st_mode))

    def test_invalid_existing_token_fails_closed(self) -> None:
        self.velvet.write_text(
            "GH_TOKEN=velvet\nHERMES_SANDBOX_LAUNCHER_TOKEN=short\n",
            encoding="utf-8",
        )
        with self.assertRaises(self.module.TokenError):
            self.module.ensure_project_token(self.velvet)

    def test_root_secret_body_contains_only_project_tokens(self) -> None:
        velvet = "v" * 48
        maximum = "m" * 48
        with patch.object(
            self.module,
            "ensure_project_token",
            side_effect=(velvet, maximum),
        ), patch.object(os, "chown"):
            with patch.object(sys, "argv", ["tool", str(self.velvet), str(self.maximum), str(self.secrets)]):
                self.module.main()
        text = self.secrets.read_text(encoding="utf-8")
        self.assertEqual(
            {
                "HERMES_SANDBOX_VELVET_TOKEN=" + velvet,
                "HERMES_SANDBOX_MAX_TOKEN=" + maximum,
            },
            set(text.splitlines()),
        )
        self.assertNotIn("GH_TOKEN", text)
        self.assertEqual(0o600, stat.S_IMODE(self.secrets.stat().st_mode))


class LauncherIdleGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module("launcher_idle_helper_test", IDLE_MODULE)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(self.module, "ROOT", self.root)
        self.root_patch.start()

    def tearDown(self) -> None:
        self.root_patch.stop()
        self.temp.cleanup()

    def write_run(self, project: str, run_id: str, status: str) -> None:
        target = self.root / "codex-runs" / project
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{run_id}.json").write_text(
            json.dumps({"run_id": run_id, "status": status}),
            encoding="utf-8",
        )

    def test_terminal_ledgers_and_no_containers_are_idle(self) -> None:
        self.write_run("velvet", "a" * 32, "completed")
        self.write_run("max", "b" * 32, "failed")
        self.assertEqual([], self.module.active_ledger_runs())
        with patch.object(
            self.module.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ):
            self.assertEqual([], self.module.active_sandbox_containers())

    def test_nonterminal_ledger_blocks_rollout(self) -> None:
        self.write_run("velvet", "a" * 32, "running")
        self.assertEqual(
            ["velvet:" + "a" * 32 + ":running"],
            self.module.active_ledger_runs(),
        )

    def test_active_disposable_container_blocks_rollout(self) -> None:
        with patch.object(
            self.module.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, "container-id\n", ""),
        ):
            self.assertEqual(["container-id"], self.module.active_sandbox_containers())

    def test_damaged_ledger_fails_closed(self) -> None:
        target = self.root / "codex-runs" / "velvet"
        target.mkdir(parents=True)
        (target / "bad.json").write_text("not-json", encoding="utf-8")
        with self.assertRaises(self.module.IdleError):
            self.module.active_ledger_runs()


if __name__ == "__main__":
    unittest.main()
