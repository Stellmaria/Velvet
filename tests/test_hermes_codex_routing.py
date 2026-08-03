from __future__ import annotations

import importlib.util
import sys
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
routing = load_module(
    "codex_routed_runner_test_module",
    ROOT / "deploy/hermes-coders/codex_routed_runner.py",
)
ALLOWED = ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")


class CodexModelRoutingTests(unittest.TestCase):
    def decision(self, prompt: str, **metadata):
        return routing.route_task(prompt, allowed_models=ALLOWED, **metadata)

    def test_small_general_and_code_keep_separate_provider_routes(self) -> None:
        general = self.decision(
            "Сделай короткую read-only сводку",
            task_type="general",
            complexity="small",
            risk="low",
            mutation_policy="read_only",
            requested_tier="small",
        )
        code = self.decision(
            "Исправь один bounded test",
            task_type="code",
            complexity="small",
            risk="medium",
            mutation_policy="workspace_write",
            requested_tier="small",
        )
        self.assertEqual("gpt-5.6-luna", general.selected_primary_model)
        self.assertEqual("gpt-5.6-luna", code.selected_primary_model)
        self.assertEqual(
            "byesu_provider:gpt-5.6-luna>gpt-5.6-terra",
            general.selected_provider_route,
        )
        self.assertEqual(
            "byesu_provider:gpt-5.4-mini>gpt-5.6-terra",
            code.selected_provider_route,
        )

    def test_standard_code_uses_terra_without_luna_downgrade(self) -> None:
        decision = self.decision(
            "Исправь callback и добавь regression test",
            task_type="code",
            complexity="standard",
            risk="medium",
            mutation_policy="workspace_write",
            requested_tier="standard",
        )
        self.assertEqual("gpt-5.6-terra", decision.selected_primary_model)
        self.assertEqual(
            ("gpt-5.6-terra", "gpt-5.6-sol"),
            routing.primary_model_order(
                decision.selected_primary_model, decision.requested_tier
            ),
        )
        self.assertNotIn(
            "gpt-5.6-luna",
            routing.primary_model_order(
                decision.selected_primary_model, decision.requested_tier
            ),
        )
        self.assertEqual(
            ("gpt-5.6-terra",),
            routing.provider_route_for("standard", "code"),
        )

    def test_complex_and_high_risk_require_sol_and_isolated_pr(self) -> None:
        for tier, risk in (("complex", "medium"), ("high_risk", "high")):
            with self.subTest(tier=tier):
                decision = self.decision(
                    "Cross-service security migration",
                    task_type="code",
                    complexity="complex",
                    risk=risk,
                    mutation_policy="isolated_pr_only",
                    requested_tier=tier,
                )
                self.assertEqual("gpt-5.6-sol", decision.selected_primary_model)
                self.assertEqual(
                    ("gpt-5.6-sol",),
                    routing.primary_model_order("gpt-5.6-sol", tier),
                )
                self.assertEqual(
                    ("gpt-5.6-terra",),
                    routing.provider_route_for(tier, "code"),
                )
                self.assertTrue(decision.review_required)
                self.assertTrue(decision.degraded_provider_route)
                self.assertEqual("isolated_pr_only", decision.mutation_policy)

    def test_explicit_model_and_tier_directives_are_validated(self) -> None:
        decision = self.decision(
            "/tier small\n/model terra\nИсправь один тест",
            task_type="code",
            complexity="small",
            risk="medium",
            mutation_policy="workspace_write",
        )
        self.assertEqual("small", decision.requested_tier)
        self.assertEqual("gpt-5.6-terra", decision.selected_primary_model)

        with self.assertRaises(base.RunnerError):
            self.decision(
                "/tier standard\n/model luna\nИсправь callback",
                task_type="code",
                complexity="standard",
                risk="medium",
                mutation_policy="workspace_write",
            )
        with self.assertRaises(base.RunnerError):
            self.decision(
                "/tier small\nИсправь тест",
                task_type="code",
                complexity="small",
                risk="medium",
                mutation_policy="workspace_write",
                requested_tier="standard",
            )

    def test_risk_is_not_derived_from_prompt_length_alone(self) -> None:
        prompt = "x" * 12_000
        decision = self.decision(
            prompt,
            task_type="read_only",
            complexity="small",
            risk="low",
            mutation_policy="read_only",
            requested_tier="small",
        )
        self.assertEqual("low", decision.risk)
        self.assertEqual("small", decision.requested_tier)

    def test_tier_below_explicit_risk_fails_closed(self) -> None:
        with self.assertRaises(base.RunnerError):
            self.decision(
                "Проверь production migration",
                task_type="code",
                complexity="standard",
                risk="high",
                mutation_policy="workspace_write",
                requested_tier="standard",
            )

    def test_legacy_inference_still_routes_bounded_docs_and_security(self) -> None:
        self.assertEqual(
            "gpt-5.6-luna",
            routing.select_model(
                "Опечатка в README",
                default="gpt-5.6-terra",
                allowed=ALLOWED,
            ),
        )
        self.assertEqual(
            "gpt-5.6-sol",
            routing.select_model(
                "Сделай полный архитектурный security рефактор нескольких сервисов",
                default="gpt-5.6-terra",
                allowed=ALLOWED,
            ),
        )

    def test_capabilities_publish_safe_routes_by_tier(self) -> None:
        manager = object.__new__(routing.RoutedCodexManager)
        manager.default_model = "gpt-5.6-terra"
        manager.allowed_models = ALLOWED
        with patch.object(
            routing.CodexManager,
            "capabilities",
            autospec=True,
            return_value={"provider": "test"},
        ):
            payload = routing.RoutedCodexManager.capabilities(manager)
        routes = payload["routing"]["routes_by_tier"]
        self.assertEqual("gpt-5.6-luna", routes["small"]["primary_model"])
        self.assertEqual("gpt-5.6-terra", routes["standard"]["primary_model"])
        self.assertEqual("gpt-5.6-sol", routes["high_risk"]["primary_model"])
        serialized = str(payload)
        self.assertNotIn("API_KEY", serialized)
        self.assertNotIn("env_key", serialized)
        self.assertFalse(payload["routing"]["downgrade_allowed"])

    def test_runtime_uses_provider_chain_for_velvet_and_max(self) -> None:
        compose = (ROOT / "deploy/hermes-coders/compose.runtime.yaml").read_text(
            encoding="utf-8"
        )
        self.assertEqual(2, compose.count("/app/codex_provider_chain_runner.py"))
        self.assertIn("Actual order is selected from immutable requested_tier", compose)


if __name__ == "__main__":
    unittest.main()
