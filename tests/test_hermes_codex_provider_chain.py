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
    "codex_provider_chain_runner_test",
    ROOT / "deploy/hermes-coders/codex_provider_chain_runner.py",
)


def failed(message: str, *, execution_started: bool = False):
    return {
        "returncode": 1,
        "stdout": "",
        "stderr": message,
        "cancelled": False,
        "execution_started": execution_started,
    }


def succeeded():
    return {
        "returncode": 0,
        "stdout": "{}",
        "stderr": "",
        "cancelled": False,
        "execution_started": False,
    }


class ProviderChainTests(unittest.TestCase):
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
        self.env = {
            "CODEX_RUNNER_API_KEY": "r" * 48,
            "CODEX_HOME": str(codex_home),
            "CODEX_WORKSPACE": str(workspace),
            "CODEX_RUN_ROOT": str(root / "runs"),
            "CODEX_ALLOWED_MODELS": "gpt-5.6-luna,gpt-5.6-terra,gpt-5.6-sol",
            "CODEX_DEFAULT_MODEL": "gpt-5.6-terra",
            "CODEX_PROVIDER_FALLBACK_ENABLED": "true",
            "CODEX_PROVIDER_FALLBACK_MODELS": (
                "gpt-5.4-mini,gpt-5.6-terra,gpt-5.6-luna"
            ),
            "BYESU_HERMES_CODEX_API_KEY": "a" * 48,
            "BYESU_HERMES_GPT_PRO_API_KEY": "b" * 48,
        }
        self.patch = patch.dict(os.environ, self.env, clear=False)
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()
        self.temp.cleanup()

    def manager(self):
        manager = provider.ProviderChainManager()
        manager._fingerprint = lambda: "stable"
        manager._cooling_down = lambda: False
        manager._open_cooldown = lambda: None
        return manager

    def seed(
        self,
        manager,
        *,
        tier: str,
        task_type: str,
        selected_model: str,
    ) -> None:
        manager.store.write(
            {
                "run_id": "a" * 32,
                "status": "queued",
                "stop_requested": False,
                "requested_tier": tier,
                "task_type": task_type,
                "complexity": "complex" if tier in {"complex", "high_risk"} else tier,
                "risk": "high" if tier == "high_risk" else "medium",
                "mutation_policy": (
                    "isolated_pr_only"
                    if tier in {"complex", "high_risk"}
                    else "workspace_write"
                ),
                "selected_primary_model": selected_model,
                "selected_provider_route": routed.provider_route_name(tier, task_type),
                "attempted_models": [],
                "attempted_routes": [],
                "mutation_started": False,
            }
        )

    def execute(
        self,
        *,
        tier: str,
        task_type: str,
        selected_model: str,
        primary_results: dict[str, dict],
        provider_results: dict[str, dict],
        mutate_on: str | None = None,
    ):
        manager = self.manager()
        self.seed(
            manager,
            tier=tier,
            task_type=task_type,
            selected_model=selected_model,
        )
        attempts: list[tuple[str, str]] = []
        state = {"fingerprint": "stable"}
        manager._fingerprint = lambda: state["fingerprint"]

        def primary_run(run_id, model, prompt):
            attempts.append(("primary", model))
            result = primary_results[model]
            if mutate_on == f"primary:{model}":
                state["fingerprint"] = "changed"
            if result.get("execution_started"):
                manager._primary_output_started = True
            return result

        def provider_run(run_id, prompt, model):
            attempts.append(("provider", model))
            result = provider_results[model]
            if mutate_on == f"provider:{model}":
                state["fingerprint"] = "changed"
            return result

        def success(run_id, model, models, routes, route, reason, stdout):
            manager.store.update(
                run_id,
                status="completed",
                model=model,
                attempted_models=models,
                attempted_routes=routes,
                actual_route=route,
                fallback_reason=reason,
            )

        manager._run_once = primary_run
        manager._provider_run = provider_run
        manager._success = success
        manager._execute("a" * 32, "task", "", selected_model)
        return manager.store.read("a" * 32), attempts

    def test_catalog_parser_is_strict(self) -> None:
        self.assertEqual(
            ("gpt-5.4-mini", "gpt-5.6-terra", "gpt-5.6-luna"),
            provider.parse_provider_models(None, None),
        )
        for value in (
            "gpt-5.6-sol",
            "gpt-5.4-mini,gpt-5.4-mini",
            "gpt-5.4-mini,",
        ):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                provider.parse_provider_models(value, None)

    def test_capabilities_publish_routes_without_secret_names(self) -> None:
        payload = self.manager().capabilities()
        fallback = payload["routing"]["provider_fallback"]
        self.assertEqual(
            ["gpt-5.4-mini", "gpt-5.6-terra"],
            fallback["routes_by_tier"]["small_code"],
        )
        self.assertEqual(
            ["gpt-5.6-terra"], fallback["routes_by_tier"]["high_risk"]
        )
        serialized = str(fallback)
        self.assertNotIn("env_key", serialized)
        self.assertNotIn("API_KEY", serialized)
        self.assertEqual("fail_closed", fallback["model_access_failure"])

    def test_small_general_uses_provider_luna(self) -> None:
        record, attempts = self.execute(
            tier="small",
            task_type="general",
            selected_model="gpt-5.6-luna",
            primary_results={
                "gpt-5.6-luna": failed("401 authentication failed")
            },
            provider_results={"gpt-5.6-luna": succeeded()},
        )
        self.assertEqual(
            [("primary", "gpt-5.6-luna"), ("provider", "gpt-5.6-luna")],
            attempts,
        )
        self.assertEqual("completed", record["status"])

    def test_small_code_capacity_retries_mini_then_terra(self) -> None:
        primary_capacity = {
            model: failed("503 capacity")
            for model in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")
        }
        record, attempts = self.execute(
            tier="small",
            task_type="code",
            selected_model="gpt-5.6-luna",
            primary_results=primary_capacity,
            provider_results={
                "gpt-5.4-mini": failed("temporarily unavailable capacity"),
                "gpt-5.6-terra": succeeded(),
            },
        )
        provider_attempts = [model for route, model in attempts if route == "provider"]
        self.assertEqual(["gpt-5.4-mini", "gpt-5.6-terra"], provider_attempts)
        self.assertEqual("gpt-5.6-terra", record["model"])
        self.assertNotIn("gpt-5.6-luna", provider_attempts)

    def test_standard_provider_route_never_downgrades_to_luna(self) -> None:
        record, attempts = self.execute(
            tier="standard",
            task_type="code",
            selected_model="gpt-5.6-terra",
            primary_results={
                "gpt-5.6-terra": failed("503 capacity"),
                "gpt-5.6-sol": failed("503 capacity"),
            },
            provider_results={"gpt-5.6-terra": succeeded()},
        )
        self.assertEqual("completed", record["status"])
        self.assertEqual(
            ["gpt-5.6-terra"],
            [model for route, model in attempts if route == "provider"],
        )
        self.assertNotIn("gpt-5.6-luna", record["attempted_models"])

    def test_sol_unavailable_uses_review_required_terra_route(self) -> None:
        record, attempts = self.execute(
            tier="high_risk",
            task_type="code",
            selected_model="gpt-5.6-sol",
            primary_results={"gpt-5.6-sol": failed("503 model unavailable")},
            provider_results={"gpt-5.6-terra": succeeded()},
        )
        self.assertEqual(
            [("primary", "gpt-5.6-sol"), ("provider", "gpt-5.6-terra")],
            attempts,
        )
        self.assertTrue(record["review_required"])
        self.assertTrue(record["degraded_provider_route"])
        self.assertEqual("completed", record["status"])

    def test_auth_blocks_entire_credential_group(self) -> None:
        primary_capacity = {
            model: failed("503 capacity")
            for model in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")
        }
        record, attempts = self.execute(
            tier="small",
            task_type="code",
            selected_model="gpt-5.6-luna",
            primary_results=primary_capacity,
            provider_results={
                "gpt-5.4-mini": failed("401 authentication failed"),
                "gpt-5.6-terra": succeeded(),
            },
        )
        self.assertEqual(
            ["gpt-5.4-mini"],
            [model for route, model in attempts if route == "provider"],
        )
        self.assertEqual("failed", record["status"])

    def test_permanent_mini_access_failure_fails_closed(self) -> None:
        primary_capacity = {
            model: failed("503 capacity")
            for model in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")
        }
        record, attempts = self.execute(
            tier="small",
            task_type="code",
            selected_model="gpt-5.6-luna",
            primary_results=primary_capacity,
            provider_results={
                "gpt-5.4-mini": failed("model not found; not entitled"),
                "gpt-5.6-terra": succeeded(),
            },
        )
        self.assertEqual(
            ["gpt-5.4-mini"],
            [model for route, model in attempts if route == "provider"],
        )
        self.assertEqual("failed", record["status"])

    def test_mutation_or_execution_event_blocks_cross_model_retry(self) -> None:
        for mutation, execution in ((True, False), (False, True)):
            with self.subTest(mutation=mutation, execution=execution):
                record, attempts = self.execute(
                    tier="standard",
                    task_type="code",
                    selected_model="gpt-5.6-terra",
                    primary_results={
                        "gpt-5.6-terra": failed(
                            "503 capacity", execution_started=execution
                        ),
                        "gpt-5.6-sol": failed("503 capacity"),
                    },
                    provider_results={"gpt-5.6-terra": succeeded()},
                    mutate_on=("primary:gpt-5.6-terra" if mutation else None),
                )
                self.assertEqual(
                    [("primary", "gpt-5.6-terra")],
                    attempts,
                )
                self.assertEqual("failed", record["status"])
                self.assertEqual(mutation, bool(record["mutation_started"]))


if __name__ == "__main__":
    unittest.main()
