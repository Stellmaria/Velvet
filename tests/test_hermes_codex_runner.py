from __future__ import annotations

import importlib.util
import json
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


runner = load_module(
    "hermes_codex_runner_test_module",
    ROOT / "deploy/hermes-coders/codex_runner.py",
)


class CodexRoutingTests(unittest.TestCase):
    def test_verified_models_are_the_only_allowed_models(self) -> None:
        self.assertEqual(
            ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"),
            runner.parse_models(None),
        )
        with self.assertRaises(RuntimeError):
            runner.parse_models("gpt-5.3-codex")

    def test_fallback_order_prefers_stronger_model_after_luna(self) -> None:
        allowed = runner.parse_models(None)
        self.assertEqual(
            ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"),
            runner.fallback_order("gpt-5.6-luna", allowed),
        )
        self.assertEqual(
            ("gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna"),
            runner.fallback_order("gpt-5.6-terra", allowed),
        )

    def test_jsonl_parser_returns_last_assistant_text_and_usage(self) -> None:
        stdout = "\n".join(
            (
                json.dumps({"type": "item", "message": {"content": "working"}}),
                json.dumps(
                    {
                        "type": "completed",
                        "output_text": "STATUS: completed",
                        "usage": {"input_tokens": 42, "output_tokens": 9},
                    }
                ),
            )
        )
        output, usage, event = runner.parse_jsonl_output(stdout)
        self.assertEqual("STATUS: completed", output)
        self.assertEqual(42, usage["input_tokens"])
        self.assertEqual("completed", event["type"])

    def test_redaction_hides_environment_and_bearer_secrets(self) -> None:
        value = runner.redact(
            {
                "CODEX_RUNNER_API_KEY": "secret",
                "message": "Authorization: Bearer abcdefghijklmnop",
            }
        )
        self.assertEqual("[REDACTED]", value["CODEX_RUNNER_API_KEY"])
        self.assertNotIn("abcdefghijklmnop", value["message"])


class RunStoreTests(unittest.TestCase):
    def test_store_round_trip_uses_private_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = runner.RunStore(Path(directory))
            run_id = "a" * 32
            store.write({"run_id": run_id, "status": "queued"})
            record = store.read(run_id)
            mode = (Path(directory) / f"{run_id}.json").stat().st_mode & 0o777
        self.assertEqual("queued", record["status"])
        self.assertEqual(0o600, mode)


class CodexManagerContractTests(unittest.TestCase):
    def test_capabilities_report_codex_and_all_models(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            workspace = root / "workspace"
            runs = root / "runs"
            home.mkdir()
            workspace.mkdir()
            (workspace / ".git").mkdir()
            (home / "auth.json").write_text("{}", encoding="utf-8")
            env = {
                "CODEX_RUNNER_API_KEY": "x" * 48,
                "CODEX_HOME": str(home),
                "CODEX_WORKSPACE": str(workspace),
                "CODEX_RUN_ROOT": str(runs),
            }
            with patch.dict(os.environ, env, clear=False), patch(
                "subprocess.run"
            ) as run:
                run.return_value.stdout = "codex-cli 0.144.4\n"
                run.return_value.stderr = ""
                manager = runner.CodexManager()
                payload = manager.capabilities()
        self.assertEqual("openai-codex-cli", payload["provider"])
        self.assertTrue(payload["authenticated"])
        self.assertEqual("gpt-5.6-terra", payload["default_model"])
        self.assertEqual(list(runner._DEFAULT_MODELS), payload["models"])
        self.assertEqual(1, payload["max_concurrency"])

    def test_submit_rejects_unknown_model_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            workspace = root / "workspace"
            home.mkdir()
            workspace.mkdir()
            (workspace / ".git").mkdir()
            (home / "auth.json").write_text("{}", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "CODEX_RUNNER_API_KEY": "x" * 48,
                    "CODEX_HOME": str(home),
                    "CODEX_WORKSPACE": str(workspace),
                    "CODEX_RUN_ROOT": str(root / "runs"),
                },
                clear=False,
            ):
                manager = runner.CodexManager()
                with self.assertRaises(runner.RunnerError):
                    manager.submit({"input": "task", "model": "gpt-5.3-codex"})


if __name__ == "__main__":
    unittest.main()
