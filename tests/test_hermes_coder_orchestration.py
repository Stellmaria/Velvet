from __future__ import annotations

import ast
import importlib.util
import json
import os
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
prepare_env = load_module(
    "hermes_prepare_router_env_test_module",
    ROOT / "deploy/hermes-orchestration/prepare_router_env.py",
)


class CoderRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(
            os.environ,
            {
                "HERMES_CODER_ROUTER_CLIENT_TOKEN": "c" * 48,
                "HERMES_CODER_VELVET_TOKEN": "v" * 48,
                "HERMES_CODER_MAX_TOKEN": "m" * 48,
                "HERMES_CODER_VELVET_GITHUB_TOKEN": "g" * 48,
                "HERMES_CODER_MAX_GITHUB_TOKEN": "h" * 48,
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

    def test_pull_request_verification_is_read_only_and_fixed(self) -> None:
        router = router_mod.CoderRouter()
        sha = "a" * 40
        responses = (
            {
                "html_url": "https://github.com/Stellmaria/Velvet/pull/534",
                "title": "test",
                "state": "open",
                "draft": False,
                "merged": False,
                "mergeable": True,
                "mergeable_state": "clean",
                "head": {"sha": sha, "ref": "agent/test"},
                "base": {"ref": "main"},
                "changed_files": 3,
                "additions": 20,
                "deletions": 2,
            },
            {
                "check_runs": [
                    {
                        "name": "tests",
                        "status": "completed",
                        "conclusion": "success",
                        "details_url": "https://example.invalid/check",
                    }
                ]
            },
            {"state": "success", "statuses": []},
        )
        with patch.object(router, "github_get", side_effect=responses) as github_get:
            result = router.pull_request("velvet", 534)
        self.assertTrue(result["checks_complete"])
        self.assertTrue(result["checks_success"])
        self.assertEqual("success", result["combined_status"])
        self.assertEqual(
            ["/pulls/534", f"/commits/{sha}/check-runs", f"/commits/{sha}/status"],
            [call.args[1] for call in github_get.call_args_list],
        )

    def test_github_verifier_rejects_arbitrary_paths(self) -> None:
        router = router_mod.CoderRouter()
        target = router.targets["velvet"]
        with self.assertRaises(router_mod.RouterError):
            router.github_get(target, "/pulls/1?redirect=https://example.invalid")
        with self.assertRaises(router_mod.RouterError):
            router.github_get(target, "/../other/repo")


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

    def test_pr_command_uses_fixed_project_and_number(self) -> None:
        with patch.object(
            coderctl.RouterClient,
            "pull_request",
            return_value={"number": 49, "project": "max"},
        ) as pull_request:
            code = coderctl.main(["pr", "max", "49"])
        self.assertEqual(0, code)
        pull_request.assert_called_once_with("max", 49)


class PrepareRouterEnvTests(unittest.TestCase):
    def test_prepares_distinct_github_tokens_without_printing_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            velvet = root / "velvet.env"
            maximum = root / "max.env"
            router = root / "router.env"
            velvet.write_text("GH_TOKEN=" + "v" * 48 + "\n", encoding="utf-8")
            maximum.write_text("GH_TOKEN=" + "m" * 48 + "\n", encoding="utf-8")
            router.write_text(
                "HERMES_CODER_ROUTER_CLIENT_TOKEN="
                + "c" * 48
                + "\nHERMES_CODER_VELVET_TOKEN="
                + "a" * 48
                + "\nHERMES_CODER_MAX_TOKEN="
                + "b" * 48
                + "\nHERMES_CODER_VELVET_BASE_URL=http://velvet:8642"
                + "\nHERMES_CODER_MAX_BASE_URL=http://max:8642\n",
                encoding="utf-8",
            )
            code = prepare_env.main([str(velvet), str(maximum), str(router)])
            values = prepare_env.parse_env(router)
        self.assertEqual(0, code)
        self.assertEqual("v" * 48, values["HERMES_CODER_VELVET_GITHUB_TOKEN"])
        self.assertEqual("m" * 48, values["HERMES_CODER_MAX_GITHUB_TOKEN"])


class OrchestrationDeploymentContractTests(unittest.TestCase):
    def test_router_has_no_host_access_or_production_secrets(self) -> None:
        compose = (ROOT / "deploy/hermes-orchestration/compose.yaml").read_text(
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

    def test_base_operator_compose_does_not_depend_on_orchestration(self) -> None:
        compose = (ROOT / "deploy/hermes-operator/compose.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("hermes-ops-gateway", compose)
        self.assertNotIn("hermes-coder-router", compose)
        self.assertNotIn("coders.env", compose)
        self.assertNotIn("agent-control", compose)

    def test_router_has_dedicated_systemd_lifecycle(self) -> None:
        unit = (ROOT / "deploy/systemd/hermes-coder-router.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("hermes-coders.service", unit)
        self.assertIn("hermes-operator-control.service", unit)
        self.assertIn("WorkingDirectory=/srv/velvet/deploy/hermes-orchestration", unit)
        self.assertIn("prepare_router_env.py", unit)
        self.assertIn("User=velvet", unit)
        self.assertNotIn("EnvironmentFile=/srv/hermes-operator-control/coders.env", unit)
        self.assertNotIn("User=root", unit)

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
        self.assertIn("Orchestration credentials prepared without printing", source)
        self.assertIn("chmod 0600", source)
        self.assertIn("coderctl.py health all", source)
        self.assertNotIn("cat \"$CODER_ROUTER_ENV\"", source)
        self.assertNotIn("echo \"$API_SERVER_KEY\"", source)

    def test_python_and_bash_sources_parse(self) -> None:
        for path in (
            ROOT / "deploy/hermes-operator/coder_router.py",
            ROOT / "deploy/hermes-operator/coderctl.py",
            ROOT / "deploy/hermes-orchestration/prepare_router_env.py",
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
