from __future__ import annotations

import ast
import importlib.util
import json
import shutil
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


class OrchestrationDeploymentContractTests(unittest.TestCase):
    def test_router_has_no_host_access_or_production_secrets(self) -> None:
        compose = (ROOT / "deploy/hermes-operator/compose.yaml").read_text(
            encoding="utf-8"
        )
        router = compose.split("  hermes-coder-router:", 1)[1].split(
            "\nnetworks:", 1
        )[0]
        self.assertIn('command: ["python", "/app/coder_router.py"]', router)
        self.assertIn("read_only: true", router)
        self.assertIn("agent-control", router)
        self.assertIn("velvet-backend", router)
        self.assertNotIn("volumes:", router)
        self.assertNotIn("docker.sock", router)
        self.assertNotIn("ports:", router)
        self.assertNotIn("operator.env", router)

    def test_coder_api_is_only_on_internal_control_network(self) -> None:
        compose = (ROOT / "deploy/hermes-coders/compose.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("API_SERVER_HOST: 0.0.0.0", compose)
        self.assertIn("API_SERVER_CORS_ORIGINS: \"\"", compose)
        self.assertNotIn("API_SERVER_KEY: hermes-coder-local-healthcheck-only", compose)
        self.assertNotIn("ports:", compose)
        self.assertIn("name: ${HERMES_AGENT_CONTROL_NETWORK:-hermes-agent-control}", compose)
        velvet = compose.split("  hermes-coder-velvet:", 1)[1].split(
            "\n  max-db-proxy:", 1
        )[0]
        maximum = compose.split("  hermes-coder-max:", 1)[1].split(
            "\nnetworks:", 1
        )[0]
        self.assertIn("- agent-control", velvet)
        self.assertIn("- agent-control", maximum)

    def test_installer_generates_keys_without_printing_values(self) -> None:
        source = (ROOT / "deploy/hermes-orchestration/install.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("secrets.token_urlsafe(48)", source)
        self.assertIn('docker network create --internal "$AGENT_CONTROL_NETWORK"', source)
        self.assertIn("Coder API and router credentials prepared without printing", source)
        self.assertIn("chmod 0600", source)
        self.assertNotIn("cat \"$CODER_ROUTER_ENV\"", source)
        self.assertNotIn("echo \"$API_SERVER_KEY\"", source)

    def test_python_and_bash_sources_parse(self) -> None:
        for path in (
            ROOT / "deploy/hermes-operator/coder_router.py",
            ROOT / "deploy/hermes-operator/coderctl.py",
        ):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("bash is unavailable")
        result = subprocess.run(
            [bash, "-n", str(ROOT / "deploy/hermes-orchestration/install.sh")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
