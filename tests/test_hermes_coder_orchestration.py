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
    "coder_router",
    ROOT / "deploy/hermes-operator/coder_router.py",
)
tier_router = load_module(
    "hermes_tier_router_test_module",
    ROOT / "deploy/hermes-operator/tier_router.py",
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

    def routing(self, **changes: str) -> dict[str, str]:
        values = {
            "task_type": "code",
            "complexity": "standard",
            "risk": "medium",
            "mutation_policy": "workspace_write",
            "requested_tier": "standard",
        }
        values.update(changes)
        return values

    def test_tier_handoff_scopes_repository_and_forbids_deploy(self) -> None:
        target = router_mod.load_targets()["velvet"]
        handoff = tier_router.build_tier_handoff(
            target,
            task_id="a" * 32,
            task="Исправить обработку ошибки",
            source="incident",
            routing=self.routing(
                task_type="incident",
                complexity="complex",
                risk="high",
                mutation_policy="isolated_pr_only",
                requested_tier="high_risk",
            ),
        )
        self.assertEqual("velvet", handoff["project"])
        self.assertEqual("high_risk", handoff["requested_tier"])
        self.assertEqual("isolated_pr_only", handoff["mutation_policy"])
        self.assertIn("merge, deployment, restart, update or rollback", handoff["forbidden_actions"])
        prompt = tier_router.build_tier_prompt(
            target,
            task_id="a" * 32,
            task="Исправить обработку ошибки",
            source="incident",
            routing={key: str(handoff[key]) for key in self.routing()},
        )
        self.assertIn("Stellmaria/Velvet", prompt)
        self.assertIn("не классифицируй повторно", prompt)
        self.assertIn("memory_candidates", prompt)

    def test_tier_validation_rejects_downgrade_and_unsafe_mutation_policy(self) -> None:
        with self.assertRaises(router_mod.RouterError):
            tier_router.validate_routing_metadata(
                self.routing(
                    complexity="complex",
                    risk="high",
                    requested_tier="standard",
                )
            )
        with self.assertRaises(router_mod.RouterError):
            tier_router.validate_routing_metadata(
                self.routing(
                    complexity="complex",
                    risk="high",
                    requested_tier="high_risk",
                    mutation_policy="workspace_write",
                )
            )

    def test_submit_requires_exact_tier_metadata(self) -> None:
        router = tier_router.TierAwareCoderRouter()
        with self.assertRaises(router_mod.RouterError):
            router.submit(
                "velvet",
                {
                    "task_id": "a" * 32,
                    "task": "x",
                    "source": "incident",
                    **self.routing(),
                    "url": "http://example.invalid",
                },
            )

    def test_submit_preserves_same_contract_for_velvet_and_max(self) -> None:
        router = tier_router.TierAwareCoderRouter()
        for project in ("velvet", "max"):
            with self.subTest(project=project), patch.object(
                router,
                "upstream",
                return_value={
                    "run_id": f"run_{project}",
                    "status": "queued",
                    "selected_primary_model": "gpt-5.6-terra",
                },
            ) as upstream:
                payload = {
                    "task_id": ("a" if project == "velvet" else "b") * 32,
                    "task": "Исправить тест",
                    "source": "owner-direct",
                    **self.routing(),
                }
                result = router.submit(project, payload)
            self.assertEqual("standard", result["requested_tier"])
            forwarded = upstream.call_args.args[3]
            self.assertIn('"source": "owner-direct"', forwarded["input"])
            for key, value in self.routing().items():
                self.assertEqual(value, forwarded[key])
            self.assertEqual(
                f"orchestration-{project}-{payload['task_id']}",
                forwarded["session_id"],
            )

    def test_authentication_uses_constant_time_comparison(self) -> None:
        router = tier_router.TierAwareCoderRouter()
        router.authenticate("Bearer " + "c" * 48)
        with self.assertRaises(router_mod.RouterError):
            router.authenticate("Bearer " + "x" * 48)

    def test_pull_request_verification_is_read_only_and_fixed(self) -> None:
        router = tier_router.TierAwareCoderRouter()
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
        self.assertEqual(
            ["/pulls/534", f"/commits/{sha}/check-runs", f"/commits/{sha}/status"],
            [call.args[1] for call in github_get.call_args_list],
        )


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

    def test_submit_records_full_routing_contract(self) -> None:
        response = {
            "run_id": "run_1",
            "status": "queued",
            "selected_primary_model": "gpt-5.6-terra",
            "selected_provider_route": "byesu_provider:gpt-5.6-terra",
            "attempted_models": [],
            "attempted_routes": [],
            "actual_route": None,
            "fallback_reason": None,
            "mutation_started": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "tasks.json"
            with patch.object(
                coderctl.RouterClient,
                "submit",
                return_value=response,
            ) as submit:
                code = coderctl.main(
                    [
                        "--ledger",
                        str(ledger_path),
                        "submit",
                        "velvet",
                        "--task",
                        "Исправить тест",
                        "--task-type",
                        "code",
                        "--complexity",
                        "standard",
                        "--risk",
                        "medium",
                        "--mutation-policy",
                        "workspace_write",
                        "--tier",
                        "standard",
                    ]
                )
            self.assertEqual(0, code)
            records = json.loads(ledger_path.read_text(encoding="utf-8"))
        self.assertEqual("run_1", records[0]["run_id"])
        self.assertEqual("standard", records[0]["requested_tier"])
        self.assertEqual("gpt-5.6-terra", records[0]["selected_primary_model"])
        kwargs = submit.call_args.kwargs
        self.assertEqual("standard", kwargs["requested_tier"])
        self.assertEqual("code", kwargs["task_type"])

    def test_terminal_status_persists_route_and_structured_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = coderctl.Ledger(Path(directory) / "tasks.json")
            record = {
                "task_id": "a" * 32,
                "project": "velvet",
                "run_id": "run_1",
                "created_at": "1",
                "requested_tier": "standard",
            }
            ledger.upsert(record)
            structured = {
                "status": "completed",
                "branch": "agent/test",
                "pr": "https://example.invalid/pr/1",
                "tests": ["ok"],
                "blocker": "",
                "memory_candidates": [{"fact": "stable"}],
            }
            coderctl._update_from_status(
                ledger,
                record,
                {
                    "status": "completed",
                    "output": "STATUS: completed",
                    "structured_output": structured,
                    "attempted_models": ["gpt-5.6-terra"],
                    "attempted_routes": ["codex_subscription:gpt-5.6-terra"],
                    "actual_route": "codex_subscription",
                    "fallback_reason": None,
                    "mutation_started": True,
                },
            )
            saved = ledger.find("a" * 32)
        self.assertEqual(structured, saved["structured_output"])
        self.assertEqual("codex_subscription", saved["actual_route"])
        self.assertTrue(saved["mutation_started"])
        self.assertEqual([{"fact": "stable"}], saved["memory_candidates"])

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
        self.assertIn('command: ["python", "/app/tier_router.py"]', router)
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
        self.assertNotIn("User=root", unit)

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

    def test_python_and_bash_sources_parse(self) -> None:
        for path in (
            ROOT / "deploy/hermes-operator/coder_router.py",
            ROOT / "deploy/hermes-operator/tier_router.py",
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
