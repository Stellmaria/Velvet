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

    def test_prompt_scopes_repository_routing_and_forbids_deploy(self) -> None:
        target = router_mod.load_targets()["velvet"]
        routing = router_mod.RoutingMetadata(
            task_type="security",
            requested_tier="high_risk",
            risk="critical",
            mutation_policy="workspace_pr",
        )
        prompt = router_mod.build_task_prompt(
            target,
            task_id="a" * 32,
            task="Исправить обработку ошибки",
            source="incident",
            routing=routing,
        )
        self.assertIn("Stellmaria/Velvet", prompt)
        self.assertIn("merge, deployment, restart, update or rollback", prompt)
        self.assertIn("memory_candidates", prompt)
        self.assertIn("output schema", prompt)
        self.assertIn('"requested_tier": "high_risk"', prompt)
        handoff = router_mod.build_task_handoff(
            target,
            task_id="a" * 32,
            task="Исправить обработку ошибки",
            source="incident",
            routing=routing,
        )
        self.assertEqual("velvet", handoff["project"])
        self.assertFalse(handoff["routing"]["live_production_mutation"])
        self.assertEqual(
            {
                "task_id",
                "source",
                "project",
                "task",
                "routing",
                "context",
                "acceptance_criteria",
                "allowed_actions",
                "forbidden_actions",
                "tests",
            },
            set(handoff),
        )

    def test_resolve_routing_prefers_explicit_fields_and_safe_defaults(self) -> None:
        explicit = router_mod.resolve_routing(
            "короткий текст",
            "owner-request",
            task_type="architecture",
            requested_tier="complex",
            risk="high",
            mutation_policy="workspace_pr",
        )
        fallback = router_mod.resolve_routing(
            "Исправить обычный баг",
            "owner-request",
        )
        incident = router_mod.resolve_routing(
            "собрать логи",
            "incident",
        )
        self.assertEqual("complex", explicit.requested_tier)
        self.assertEqual(("code", "standard"), (
            fallback.task_type,
            fallback.requested_tier,
        ))
        self.assertEqual(("incident", "complex"), (
            incident.task_type,
            incident.requested_tier,
        ))

    def test_resolve_routing_rejects_under_tier_but_allows_read_only_security_review(self) -> None:
        with self.assertRaises(router_mod.RouterError):
            router_mod.resolve_routing(
                "security change",
                "owner-request",
                task_type="security",
                requested_tier="standard",
                risk="critical",
                mutation_policy="workspace_pr",
            )
        review = router_mod.resolve_routing(
            "security review без изменений",
            "owner-request",
            task_type="security",
            requested_tier="high_risk",
            risk="critical",
            mutation_policy="read_only",
        )
        self.assertEqual("read_only", review.mutation_policy)
        with self.assertRaises(router_mod.RouterError):
            router_mod.resolve_routing(
                "проверить статус",
                "owner-request",
                task_type="read_only",
                requested_tier="small",
                risk="low",
                mutation_policy="workspace_pr",
            )

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

    def test_submit_forwards_runs_contract_and_explicit_routing(self) -> None:
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
                    "task_type": "code",
                    "requested_tier": "small",
                    "risk": "low",
                    "mutation_policy": "workspace_pr",
                },
            )
        self.assertEqual("run_abc", result["run_id"])
        self.assertEqual("small", result["requested_tier"])
        args = upstream.call_args.args
        self.assertEqual("POST", args[1])
        self.assertEqual("/v1/runs", args[2])
        self.assertEqual("orchestration-max-" + "b" * 32, args[3]["session_id"])
        self.assertEqual("small", args[3]["requested_tier"])
        self.assertEqual("code", args[3]["task_type"])
        self.assertNotIn("model", args[3])

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

    def test_submit_records_explicit_router_tier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "tasks.json"
            with patch.object(
                coderctl.RouterClient,
                "submit",
                return_value={"run_id": "run_1", "status": "started"},
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
                        "--tier",
                        "small",
                        "--risk",
                        "low",
                    ]
                )
            self.assertEqual(0, code)
            records = json.loads(ledger_path.read_text(encoding="utf-8"))
            self.assertEqual("run_1", records[0]["run_id"])
            self.assertEqual("velvet", records[0]["project"])
            self.assertEqual("small", records[0]["requested_tier"])
            self.assertFalse(records[0]["live_production_mutation"])
            self.assertEqual("small", submit.call_args.kwargs["requested_tier"])

    def test_submit_defaults_to_standard_instead_of_under_routing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "tasks.json"
            with patch.object(
                coderctl.RouterClient,
                "submit",
                return_value={"run_id": "run_2", "status": "started"},
            ) as submit:
                code = coderctl.main(
                    [
                        "--ledger",
                        str(ledger_path),
                        "submit",
                        "max",
                        "--task",
                        "Исправить неизвестную задачу",
                    ]
                )
        self.assertEqual(0, code)
        self.assertEqual("standard", submit.call_args.kwargs["requested_tier"])
        self.assertEqual("code", submit.call_args.kwargs["task_type"])

    def test_submit_rejects_under_tier_before_router_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "tasks.json"
            with patch.object(coderctl.RouterClient, "submit") as submit:
                code = coderctl.main(
                    [
                        "--ledger",
                        str(ledger_path),
                        "submit",
                        "velvet",
                        "--task",
                        "security change",
                        "--task-type",
                        "security",
                        "--tier",
                        "standard",
                        "--risk",
                        "critical",
                    ]
                )
        self.assertEqual(2, code)
        submit.assert_not_called()

    def test_terminal_status_persists_routing_and_structured_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = coderctl.Ledger(Path(directory) / "tasks.json")
            record = {
                "task_id": "a" * 32,
                "project": "velvet",
                "run_id": "run_1",
                "created_at": "1",
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
                    "task_type": "code",
                    "requested_tier": "standard",
                    "selected_primary_model": "gpt-5.6-terra",
                    "actual_route": "codex_subscription",
                    "live_production_mutation": False,
                },
            )
            saved = ledger.find("a" * 32)
        self.assertEqual(structured, saved["structured_output"])
        self.assertEqual([{"fact": "stable"}], saved["memory_candidates"])
        self.assertEqual("standard", saved["requested_tier"])
        self.assertEqual("gpt-5.6-terra", saved["selected_primary_model"])

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
    def test_kael_contract_requires_explicit_tier_and_keeps_live_prod_boundary(self) -> None:
        agents = (ROOT / "deploy/hermes-operator/AGENTS.kael.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("--task-type code", agents)
        self.assertIn("--tier standard", agents)
        self.assertIn("--risk medium", agents)
        self.assertIn("--mutation-policy workspace_pr", agents)
        self.assertIn("Terra → Luna", agents)
        self.assertIn("не получают прямого доступа к live production", agents)

    def test_brain_skills_preserve_tier_and_pr_gate(self) -> None:
        orchestrated = (
            ROOT / "brain-vault/skills/orchestrated-task/SKILL.md"
        ).read_text(encoding="utf-8")
        gate = (ROOT / "brain-vault/skills/coder-pr-gate/SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("requested_tier", orchestrated)
        self.assertIn("mutation_policy=read_only", orchestrated)
        self.assertIn("degraded_execution", orchestrated)
        self.assertIn("selected_provider_route", gate)
        self.assertIn("production update", gate)

    def test_coder_contracts_preserve_tier_and_live_prod_boundary(self) -> None:
        for name in ("AGENTS.velvet.md", "AGENTS.max.md"):
            source = (ROOT / "deploy/hermes-coders" / name).read_text(
                encoding="utf-8"
            )
            self.assertIn("requested_tier", source)
            self.assertIn("Terra → Luna", source)
            self.assertIn("изолированной ветке и PR", source)
            self.assertIn("live production", source)

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
        self.assertIn('API_SERVER_CORS_ORIGINS: ""', compose)
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
        self.assertNotIn('cat "$CODER_ROUTER_ENV"', source)
        self.assertNotIn('echo "$API_SERVER_KEY"', source)

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
