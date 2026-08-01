from __future__ import annotations

import importlib.util
import json
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


coderctl = load_module(
    "hermes_coderctl_test_module",
    ROOT / "deploy/hermes-operator/coderctl.py",
)
router_mod = load_module(
    "hermes_coder_router_test_module",
    ROOT / "deploy/hermes-operator/coder_router.py",
)


class CoderRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(
            "os.environ",
            {
                "HERMES_CODER_ROUTER_CLIENT_TOKEN": "c" * 48,
                "HERMES_CODER_VELVET_TOKEN": "v" * 48,
                "HERMES_CODER_MAX_TOKEN": "m" * 48,
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_prompt_scopes_repository_and_forbids_deploy(self) -> None:
        target = router_mod.load_targets()["velvet"]
        prompt = router_mod.build_task_prompt(
            target,
            task_id="a" * 32,
            task="Исправить обработку ошибки",
            source="incident",
        )
        self.assertIn("Stellmaria/Velvet", prompt)
        self.assertIn("Не сливай его", prompt)
        self.assertIn("restart/update/rollback", prompt)
        self.assertIn("STATUS: completed|blocked|failed", prompt)

    def test_submit_accepts_only_fixed_payload(self) -> None:
        router = router_mod.CoderRouter()
        with self.assertRaises(router_mod.RouterError):
            router.submit(
                "velvet",
                {
                    "task_id": "a" * 32,
                    "task": "x",
                    "source": "incident",
                    "url": "http://example.invalid",
                },
            )

    def test_submit_forwards_only_runs_contract(self) -> None:
        router = router_mod.CoderRouter()
        with patch.object(
            router,
            "upstream",
            return_value={"run_id": "run_abc", "status": "started"},
        ) as upstream:
            result = router.submit(
                "max",
                {
                    "task_id": "b" * 32,
                    "task": "Исправить тест",
                    "source": "owner-request",
                },
            )
        self.assertEqual("run_abc", result["run_id"])
        args = upstream.call_args.args
        self.assertEqual("POST", args[1])
        self.assertEqual("/v1/runs", args[2])
        self.assertEqual("orchestration-max-" + "b" * 32, args[3]["session_id"])

    def test_authentication_uses_constant_time_comparison(self) -> None:
        router = router_mod.CoderRouter()
        router.authenticate("Bearer " + "c" * 48)
        with self.assertRaises(router_mod.RouterError):
            router.authenticate("Bearer " + "x" * 48)


class CoderCtlTests(unittest.TestCase):
    def test_redaction_hides_nested_secrets(self) -> None:
        result = coderctl.redact(
            {
                "API_KEY": "secret-value",
                "nested": {"message": "Authorization: Bearer abcdefghijklmnop"},
            }
        )
        self.assertEqual("[REDACTED]", result["API_KEY"])
        self.assertNotIn("abcdefghijklmnop", result["nested"]["message"])

    def test_ledger_upserts_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = coderctl.Ledger(Path(directory) / "tasks.json")
            ledger.upsert({"task_id": "one", "status": "started", "created_at": "1"})
            ledger.upsert({"task_id": "one", "status": "completed", "created_at": "1"})
            records = ledger.list()
        self.assertEqual(1, len(records))
        self.assertEqual("completed", records[0]["status"])

    def test_submit_records_router_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "tasks.json"
            with patch.object(
                coderctl.RouterClient,
                "submit",
                return_value={"run_id": "run_1", "status": "started"},
            ):
                code = coderctl.main(
                    [
                        "--ledger",
                        str(ledger_path),
                        "submit",
                        "velvet",
                        "--task",
                        "Исправить тест",
                    ]
                )
            self.assertEqual(0, code)
            records = json.loads(ledger_path.read_text(encoding="utf-8"))
            self.assertEqual("run_1", records[0]["run_id"])
            self.assertEqual("velvet", records[0]["project"])


if __name__ == "__main__":
    unittest.main()
