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


load_module("codex_runner", ROOT / "deploy/hermes-coders/codex_runner.py")
routing = load_module(
    "codex_routed_runner_test_module",
    ROOT / "deploy/hermes-coders/codex_routed_runner.py",
)
ALLOWED = ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")


class CodexModelRoutingTests(unittest.TestCase):
    def test_explicit_model_directive_wins(self) -> None:
        self.assertEqual(
            "gpt-5.6-luna",
            routing.select_model(
                "Исправь тест. /model luna",
                default="gpt-5.6-terra",
                allowed=ALLOWED,
            ),
        )
        self.assertEqual(
            "gpt-5.6-sol",
            routing.select_model(
                "модель: сол Проведи проверку",
                default="gpt-5.6-terra",
                allowed=ALLOWED,
            ),
        )

    def test_small_docs_task_uses_luna(self) -> None:
        self.assertEqual(
            "gpt-5.6-luna",
            routing.select_model(
                "Исправь опечатку в README",
                default="gpt-5.6-terra",
                allowed=ALLOWED,
            ),
        )

    def test_architecture_and_security_use_sol(self) -> None:
        for prompt in (
            "Сделай полный архитектурный рефактор нескольких сервисов",
            "Проведи security анализ race condition",
        ):
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    "gpt-5.6-sol",
                    routing.select_model(
                        prompt,
                        default="gpt-5.6-terra",
                        allowed=ALLOWED,
                    ),
                )

    def test_normal_task_uses_terra(self) -> None:
        self.assertEqual(
            "gpt-5.6-terra",
            routing.select_model(
                "Исправь обработку callback и добавь regression test",
                default="gpt-5.6-terra",
                allowed=ALLOWED,
            ),
        )

    def test_manager_adds_model_without_overriding_explicit_choice(self) -> None:
        manager = object.__new__(routing.RoutedCodexManager)
        manager.default_model = "gpt-5.6-terra"
        manager.allowed_models = ALLOWED
        with patch.object(
            routing.CodexManager,
            "submit",
            autospec=True,
            return_value={"status": "queued"},
        ) as submit:
            routing.RoutedCodexManager.submit(manager, {"input": "Исправь docs"})
            self.assertEqual("gpt-5.6-luna", submit.call_args.args[1]["model"])
            routing.RoutedCodexManager.submit(
                manager,
                {"input": "Исправь docs", "model": "gpt-5.6-sol"},
            )
            self.assertEqual("gpt-5.6-sol", submit.call_args.args[1]["model"])


if __name__ == "__main__":
    unittest.main()
