from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from http import HTTPStatus
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


class FakeStore:
    def __init__(self) -> None:
        self.record = {"stop_requested": False}

    def write(self, record):
        self.record = dict(record)

    def read(self, run_id: str):
        return dict(self.record)

    def update(self, run_id: str, **values):
        self.record.update(values)
        return dict(self.record)


class FakeRunnerError(RuntimeError):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def install_stubs(root: Path):
    base = types.ModuleType("codex_runner")
    base.CodexManager = object
    base.Handler = object
    base.ThreadingHTTPServer = object
    base.RunnerError = FakeRunnerError
    base.redact_text = lambda value: value
    base.utc_now = lambda: "2026-08-03T00:00:00+00:00"
    sys.modules["codex_runner"] = base

    routed = load_module(
        "codex_routed_runner",
        ROOT / "deploy/hermes-coders/codex_routed_runner.py",
    )

    class FakeRouted:
        def __init__(self):
            self.codex_bin = "codex"
            self.codex_home = root / "codex"
            self.codex_home.mkdir(parents=True, exist_ok=True)
            (self.codex_home / "AGENTS.md").write_text("agents\n", encoding="utf-8")
            (self.codex_home / "output.schema.json").write_text("{}\n", encoding="utf-8")
            (self.codex_home / "auth.json").write_text("{}\n", encoding="utf-8")
            self.workspace = root / "workspace"
            self.workspace.mkdir(parents=True, exist_ok=True)
            (self.workspace / ".git").mkdir(exist_ok=True)
            self.allowed_models = (
                "gpt-5.6-luna",
                "gpt-5.6-terra",
                "gpt-5.6-sol",
            )
            self.default_model = "gpt-5.6-terra"
            self.timeout_seconds = 60
            self._process_lock = threading.RLock()
            self._processes = {}
            self._execution_lock = threading.RLock()
            self.store = FakeStore()

        def capabilities(self):
            return {
                "routing": {
                    "default": self.default_model,
                    "small": "gpt-5.6-luna",
                    "standard": "gpt-5.6-terra",
                    "complex": "gpt-5.6-sol",
                    "high_risk": "gpt-5.6-sol",
                }
            }

    routed.RoutedCodexManager = FakeRouted

    def env_bool(name: str, default: bool = False) -> bool:
        raw = os.environ.get(name)
        return default if raw is None else raw.strip().casefold() in {"1", "true", "yes", "on"}

    def reason(output: str):
        lowered = output.casefold()
        if any(item in lowered for item in ("usage limit", "quota", "429", "rate limit")):
            return "subscription_limit"
        if any(item in lowered for item in ("authentication", "401", "403", "token expired")):
            return "subscription_auth"
        if any(item in lowered for item in ("capacity", "temporarily unavailable", "503", "not available")):
            return "codex_capacity"
        return None

    first = types.ModuleType("codex_first_runner")
    first.Handler = object
    first.ThreadingHTTPServer = object
    first.env_bool = env_bool
    first.provider_fallback_reason = reason
    sys.modules["codex_first_runner"] = first

    def execution_started(stdout: str) -> bool:
        for raw in stdout.splitlines():
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            item = event.get("item") if isinstance(event, dict) else None
            kind = str(item.get("type") or "") if isinstance(item, dict) else ""
            if kind in {"command_execution", "file_change", "mcp_tool_call"}:
                return True
            if kind.endswith("_tool_call") or kind.endswith("_execution"):
                return True
        return False

    class FakeSafe(FakeRouted):
        def _fingerprint(self):
            value = getattr(self, "_fingerprint_value", "stable")
            if getattr(self, "_run_baseline", None) is None:
                self._run_baseline = value
            return value

        def _cooling_down(self):
            return False

        def _open_cooldown(self):
            self.cooldown_opened = True

        def _run_once(self, run_id, model, prompt):
            return {
                "returncode": 1,
                "stdout": "",
                "stderr": "usage limit",
                "cancelled": False,
            }

        def _success(self, run_id, model, models, routes, route, reason, stdout):
            self.store.update(
                run_id,
                status="completed",
                model=model,
                attempted_models=models,
                attempted_routes=routes,
                actual_route=route,
                fallback_reason=reason,
                mutation_started=False,
            )

    safe = types.ModuleType("codex_first_safe_runner")
    safe.SafeCodexFirstManager = FakeSafe
    safe.primary_execution_started = execution_started
    sys.modules["codex_first_safe_runner"] = safe
    return routed


class ProviderTierRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.routed = install_stubs(Path(cls.temp.name))
        cls.module = load_module(
            "codex_provider_chain_runner_test",
            ROOT / "deploy/hermes-coders/codex_provider_chain_runner.py",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def _classification(
        self,
        *,
        task_type: str,
        tier: str,
        risk: str = "medium",
        mutation_policy: str = "workspace_pr",
    ):
        model = {
            "small": "gpt-5.6-luna",
            "standard": "gpt-5.6-terra",
            "complex": "gpt-5.6-sol",
            "high_risk": "gpt-5.6-sol",
        }[tier]
        return self.routed.TaskClassification(
            task_type=task_type,
            requested_tier=tier,
            risk=risk,
            mutation_policy=mutation_policy,
            model=model,
        )

    def test_explicit_structured_classification_wins(self) -> None:
        result = self.routed.classify_task(
            "короткий текст, который не должен менять явный tier",
            default="gpt-5.6-terra",
            allowed=("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"),
            task_type="security",
            requested_tier="high_risk",
            risk="critical",
            mutation_policy="workspace_pr",
        )
        self.assertEqual("security", result.task_type)
        self.assertEqual("high_risk", result.requested_tier)
        self.assertEqual("gpt-5.6-sol", result.model)

    def test_automatic_classification_is_safe_default(self) -> None:
        docs = self.routed.classify_task(
            "Проверь статус и составь короткую сводку документации",
            default="gpt-5.6-terra",
            allowed=("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"),
        )
        security = self.routed.classify_task(
            "Исправить race condition в авторизации и миграции схемы",
            default="gpt-5.6-terra",
            allowed=("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"),
        )
        self.assertEqual(("docs", "small", "gpt-5.6-luna"), (
            docs.task_type,
            docs.requested_tier,
            docs.model,
        ))
        self.assertEqual("high_risk", security.requested_tier)
        self.assertEqual("gpt-5.6-sol", security.model)

    def test_classification_rejects_under_tier_and_model_mismatch(self) -> None:
        allowed = ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")
        with self.assertRaises(ValueError):
            self.routed.classify_task(
                "security change",
                default="gpt-5.6-terra",
                allowed=allowed,
                task_type="security",
                requested_tier="standard",
                risk="critical",
                mutation_policy="workspace_pr",
            )
        with self.assertRaises(ValueError):
            self.routed.classify_task(
                "ordinary code",
                default="gpt-5.6-terra",
                allowed=allowed,
                model="gpt-5.6-luna",
                task_type="code",
                requested_tier="standard",
                risk="medium",
                mutation_policy="workspace_pr",
            )

    def test_small_code_is_low_risk_and_read_only_policy_is_independent(self) -> None:
        allowed = ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")
        small = self.routed.classify_task(
            "Исправить одну опечатку в коде",
            default="gpt-5.6-terra",
            allowed=allowed,
        )
        review = self.routed.classify_task(
            "Провести security review без изменений",
            default="gpt-5.6-terra",
            allowed=allowed,
            task_type="security",
            requested_tier="high_risk",
            risk="critical",
            mutation_policy="read_only",
        )
        self.assertEqual(("code", "low", "small"), (
            small.task_type, small.risk, small.requested_tier
        ))
        self.assertEqual("read_only", review.mutation_policy)
        with self.assertRaises(ValueError):
            self.routed.classify_task(
                "Проверить статус",
                default="gpt-5.6-terra",
                allowed=allowed,
                task_type="read_only",
                requested_tier="small",
                risk="low",
                mutation_policy="workspace_pr",
            )

    def test_provider_routes_are_tier_aware_and_never_terra_to_luna(self) -> None:
        configured = ("gpt-5.4-mini", "gpt-5.6-terra", "gpt-5.6-luna")
        cases = {
            ("code", "small"): ("gpt-5.4-mini", "gpt-5.6-terra"),
            ("read_only", "small"): ("gpt-5.6-luna", "gpt-5.6-terra"),
            ("code", "standard"): ("gpt-5.6-terra",),
            ("architecture", "complex"): ("gpt-5.6-terra",),
            ("security", "high_risk"): ("gpt-5.6-terra",),
        }
        for (task_type, tier), expected in cases.items():
            with self.subTest(task_type=task_type, tier=tier):
                route = self.module.provider_route_for(
                    self._classification(task_type=task_type, tier=tier),
                    configured,
                )
                self.assertEqual(expected, route.models)
                self.assertFalse(
                    route.models
                    and route.models[0] == "gpt-5.6-terra"
                    and "gpt-5.6-luna" in route.models[1:]
                )

    def test_complex_and_high_risk_provider_routes_require_review(self) -> None:
        configured = ("gpt-5.4-mini", "gpt-5.6-terra", "gpt-5.6-luna")
        for task_type, tier in (("architecture", "complex"), ("security", "high_risk")):
            route = self.module.provider_route_for(
                self._classification(task_type=task_type, tier=tier),
                configured,
            )
            self.assertTrue(route.degraded)
            self.assertTrue(route.review_required)
            self.assertEqual(("gpt-5.6-terra",), route.models)

    def _manager(self):
        env = {
            "CODEX_PROVIDER_FALLBACK_ENABLED": "true",
            "CODEX_PROVIDER_FALLBACK_MODELS": "gpt-5.4-mini,gpt-5.6-terra,gpt-5.6-luna",
            "BYESU_HERMES_CODEX_API_KEY": "a" * 48,
            "BYESU_HERMES_GPT_PRO_API_KEY": "b" * 48,
        }
        with patch.dict(os.environ, env, clear=False):
            return self.module.ProviderChainManager()

    def test_submit_persists_explicit_tier_and_selected_routes(self) -> None:
        manager = self._manager()
        with patch.object(self.module.threading, "Thread") as thread:
            record = manager.submit(
                {
                    "input": "Исправить обычный баг",
                    "session_id": "test-session",
                    "task_type": "code",
                    "requested_tier": "standard",
                    "risk": "medium",
                    "mutation_policy": "workspace_pr",
                }
            )
        self.assertEqual("standard", record["requested_tier"])
        self.assertEqual("gpt-5.6-terra", record["selected_primary_model"])
        self.assertEqual(["gpt-5.6-terra"], record["selected_primary_route"])
        self.assertEqual(["gpt-5.6-terra"], record["selected_provider_route"])
        self.assertFalse(record["live_production_mutation"])
        thread.return_value.start.assert_called_once_with()

    def test_capabilities_publish_safe_routes_by_tier(self) -> None:
        fallback = self._manager().capabilities()["routing"]["provider_fallback"]
        self.assertEqual(
            ["gpt-5.4-mini", "gpt-5.6-terra"],
            fallback["routes_by_tier"]["small_code"]["models"],
        )
        self.assertEqual(
            ["gpt-5.6-luna", "gpt-5.6-terra"],
            fallback["routes_by_tier"]["small_general"]["models"],
        )
        self.assertEqual(
            ["gpt-5.6-terra"],
            fallback["routes_by_tier"]["standard"]["models"],
        )
        self.assertTrue(fallback["routes_by_tier"]["complex"]["review_required"])
        self.assertFalse(fallback["downgrade_allowed"])
        self.assertFalse(fallback["live_production_mutation"])
        self.assertNotIn("env_key", str(fallback))

    def _execute_provider(self, classification, results):
        manager = self._manager()
        manager.store.record = {
            "stop_requested": False,
            "task_type": classification.task_type,
            "requested_tier": classification.requested_tier,
            "risk": classification.risk,
            "mutation_policy": classification.mutation_policy,
            "selected_primary_model": classification.model,
            "model": classification.model,
            "review_required": False,
        }
        attempts = []

        def provider_run(run_id, prompt, model):
            attempts.append(model)
            return results[model]

        manager._provider_run = provider_run
        manager._execute("run", "task", "", classification.model)
        return manager, attempts

    def test_small_code_capacity_escalates_only_to_terra(self) -> None:
        fail = {
            "returncode": 1,
            "stdout": "",
            "stderr": "capacity",
            "cancelled": False,
            "execution_started": False,
        }
        success = {
            "returncode": 0,
            "stdout": "{}",
            "stderr": "",
            "cancelled": False,
            "execution_started": False,
        }
        manager, attempts = self._execute_provider(
            self._classification(task_type="code", tier="small"),
            {
                "gpt-5.4-mini": fail,
                "gpt-5.6-terra": success,
            },
        )
        self.assertEqual(["gpt-5.4-mini", "gpt-5.6-terra"], attempts)
        self.assertEqual("completed", manager.store.record["status"])
        self.assertNotIn("gpt-5.6-luna", attempts)

    def test_standard_and_complex_provider_use_only_terra(self) -> None:
        success = {
            "returncode": 0,
            "stdout": "{}",
            "stderr": "",
            "cancelled": False,
            "execution_started": False,
        }
        for classification in (
            self._classification(task_type="code", tier="standard"),
            self._classification(task_type="architecture", tier="complex", risk="high"),
        ):
            with self.subTest(tier=classification.requested_tier):
                manager, attempts = self._execute_provider(
                    classification,
                    {"gpt-5.6-terra": success},
                )
                self.assertEqual(["gpt-5.6-terra"], attempts)
                self.assertEqual("completed", manager.store.record["status"])

    def test_auth_failure_skips_same_credential_group(self) -> None:
        auth = {
            "returncode": 1,
            "stdout": "",
            "stderr": "401 authentication failed",
            "cancelled": False,
            "execution_started": False,
        }
        manager, attempts = self._execute_provider(
            self._classification(task_type="code", tier="small"),
            {
                "gpt-5.4-mini": auth,
                "gpt-5.6-terra": auth,
            },
        )
        self.assertEqual(["gpt-5.4-mini"], attempts)
        self.assertEqual("failed", manager.store.record["status"])

    def test_source_keeps_mutation_execution_and_live_prod_guards(self) -> None:
        source = (
            ROOT / "deploy/hermes-coders/codex_provider_chain_runner.py"
        ).read_text(encoding="utf-8")
        self.assertIn("self._fingerprint() != baseline", source)
        self.assertIn("primary_execution_started", source)
        self.assertIn('"live_production_mutation": False', source)
        self.assertIn('"downgrade_allowed": False', source)
        self.assertNotIn(
            '("gpt-5.6-terra", "gpt-5.6-luna")',
            source,
        )


if __name__ == "__main__":
    unittest.main()
