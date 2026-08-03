from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
import types
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


class FakeStore:
    def __init__(self) -> None:
        self.record = {"stop_requested": False}

    def read(self, run_id: str):
        return dict(self.record)

    def update(self, run_id: str, **values):
        self.record.update(values)


def install_stubs(root: Path) -> None:
    base = types.ModuleType("codex_runner")
    base.redact_text = lambda value: value
    base.utc_now = lambda: "2026-08-03T00:00:00+00:00"
    sys.modules["codex_runner"] = base

    class FakeRouted:
        def __init__(self):
            self.codex_bin = "codex"
            self.codex_home = root / "codex"
            self.codex_home.mkdir(parents=True, exist_ok=True)
            (self.codex_home / "AGENTS.md").write_text("agents\n", encoding="utf-8")
            (self.codex_home / "output.schema.json").write_text("{}\n", encoding="utf-8")
            self.workspace = root / "workspace"
            self.workspace.mkdir(parents=True, exist_ok=True)
            self.allowed_models = (
                "gpt-5.6-luna",
                "gpt-5.6-terra",
                "gpt-5.6-sol",
            )
            self.default_model = "gpt-5.6-terra"
            self.timeout_seconds = 60
            self._process_lock = threading.RLock()
            self._processes = {}
            self._execution_lock = threading.Lock()
            self.store = FakeStore()

        def capabilities(self):
            return {"routing": {"default": self.default_model}}

    routed = types.ModuleType("codex_routed_runner")
    routed.RoutedCodexManager = FakeRouted
    sys.modules["codex_routed_runner"] = routed

    def env_bool(name: str, default: bool = False) -> bool:
        raw = os.environ.get(name)
        return default if raw is None else raw.strip().casefold() in {"1", "true", "yes", "on"}

    def reason(output: str):
        lowered = output.casefold()
        if any(item in lowered for item in ("usage limit", "quota", "429", "rate limit")):
            return "subscription_limit"
        if any(item in lowered for item in ("authentication", "401", "403", "token expired")):
            return "subscription_auth"
        if any(item in lowered for item in ("capacity", "temporarily unavailable", "503")):
            return "codex_capacity"
        return None

    class FakeCodexFirst(FakeRouted):
        def _execute(self, run_id, prompt, instructions, selected_model):
            self.store.update(
                run_id,
                status="failed",
                attempted_models=[selected_model],
                attempted_routes=[f"codex_subscription:{selected_model}"],
                actual_route="codex_subscription",
                fallback_reason="subscription_limit",
                mutation_started=False,
                error="codex subscription usage limit",
            )

    first = types.ModuleType("codex_first_runner")
    first.CodexFirstManager = FakeCodexFirst
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

    class FakeSafe(FakeCodexFirst):
        def _fingerprint(self):
            value = "stable"
            if getattr(self, "_run_baseline", None) is None:
                self._run_baseline = value
            return value

        def _success(self, run_id, model, models, routes, route, reason, stdout):
            self.store.update(
                run_id,
                status="completed",
                model=model,
                attempted_models=models,
                attempted_routes=routes,
                actual_route=route,
                fallback_reason=reason,
            )

    safe = types.ModuleType("codex_first_safe_runner")
    safe.SafeCodexFirstManager = FakeSafe
    safe.primary_execution_started = execution_started
    sys.modules["codex_first_safe_runner"] = safe


class ProviderChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        install_stubs(Path(cls.temp.name))
        cls.module = load_module(
            "codex_provider_chain_runner_test",
            ROOT / "deploy/hermes-coders/codex_provider_chain_runner.py",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_default_legacy_and_strict_allowlist(self) -> None:
        self.assertEqual(
            ("gpt-5.4-mini", "gpt-5.6-terra", "gpt-5.6-luna"),
            self.module.parse_provider_models(None, None),
        )
        self.assertEqual(
            ("gpt-5.6-terra",),
            self.module.parse_provider_models("", "gpt-5.6-terra"),
        )
        for raw in ("gpt-5.6-sol", "gpt-5.4-mini,gpt-5.4-mini", "gpt-5.4-mini,"):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                self.module.parse_provider_models(raw, None)

    def _manager(self):
        env = {
            "CODEX_PROVIDER_FALLBACK_ENABLED": "true",
            "CODEX_PROVIDER_FALLBACK_MODELS": "gpt-5.4-mini,gpt-5.6-terra,gpt-5.6-luna",
            "BYESU_HERMES_CODEX_API_KEY": "a" * 48,
            "BYESU_HERMES_GPT_PRO_API_KEY": "b" * 48,
        }
        with patch.dict(os.environ, env, clear=False):
            return self.module.ProviderChainManager()

    def test_homes_use_two_credentials_without_secret_values(self) -> None:
        manager = self._manager()
        configs = {
            model: (home / "config.toml").read_text(encoding="utf-8")
            for model, home in manager.provider_homes.items()
        }
        self.assertIn('env_key = "BYESU_HERMES_CODEX_API_KEY"', configs["gpt-5.4-mini"])
        self.assertIn('env_key = "BYESU_HERMES_CODEX_API_KEY"', configs["gpt-5.6-terra"])
        self.assertIn('env_key = "BYESU_HERMES_GPT_PRO_API_KEY"', configs["gpt-5.6-luna"])
        joined = "\n".join(configs.values())
        self.assertNotIn("a" * 48, joined)
        self.assertNotIn("b" * 48, joined)
        self.assertNotIn('"GH_TOKEN"', joined)

    def test_capabilities_expose_order_and_safe_groups(self) -> None:
        fallback = self._manager().capabilities()["routing"]["provider_fallback"]
        self.assertEqual("gpt-5.4-mini", fallback["model"])
        self.assertEqual(
            ["gpt-5.4-mini", "gpt-5.6-terra", "gpt-5.6-luna"],
            fallback["models"],
        )
        self.assertEqual(
            [
                {"name": "byesu-coder", "models": ["gpt-5.4-mini", "gpt-5.6-terra"]},
                {"name": "byesu-gpt-pro", "models": ["gpt-5.6-luna"]},
            ],
            fallback["credential_groups"],
        )
        self.assertNotIn("env_key", str(fallback))

    def _execute(self, results):
        manager = self._manager()
        attempts = []

        def provider_run(run_id, prompt, model):
            attempts.append(model)
            return results[model]

        manager._provider_run = provider_run
        manager._execute("run", "task", "", "gpt-5.6-terra")
        return manager, attempts

    def test_capacity_walks_full_chain(self) -> None:
        fail = {"returncode": 1, "stdout": "", "stderr": "capacity", "cancelled": False, "execution_started": False}
        success = {"returncode": 0, "stdout": "{}", "stderr": "", "cancelled": False, "execution_started": False}
        manager, attempts = self._execute({
            "gpt-5.4-mini": fail,
            "gpt-5.6-terra": fail,
            "gpt-5.6-luna": success,
        })
        self.assertEqual(["gpt-5.4-mini", "gpt-5.6-terra", "gpt-5.6-luna"], attempts)
        self.assertEqual("completed", manager.store.record["status"])

    def test_auth_skips_same_credential_group(self) -> None:
        auth = {"returncode": 1, "stdout": "", "stderr": "401 authentication failed", "cancelled": False, "execution_started": False}
        success = {"returncode": 0, "stdout": "{}", "stderr": "", "cancelled": False, "execution_started": False}
        manager, attempts = self._execute({
            "gpt-5.4-mini": auth,
            "gpt-5.6-terra": success,
            "gpt-5.6-luna": success,
        })
        self.assertEqual(["gpt-5.4-mini", "gpt-5.6-luna"], attempts)
        self.assertEqual("completed", manager.store.record["status"])

    def test_ordinary_error_and_execution_event_stop_chain(self) -> None:
        for result in (
            {"returncode": 1, "stdout": "", "stderr": "pytest assertion failed", "cancelled": False, "execution_started": False},
            {"returncode": 1, "stdout": "", "stderr": "blocked", "cancelled": False, "execution_started": True},
        ):
            with self.subTest(result=result):
                manager, attempts = self._execute({
                    "gpt-5.4-mini": result,
                    "gpt-5.6-terra": result,
                    "gpt-5.6-luna": result,
                })
                self.assertEqual(["gpt-5.4-mini"], attempts)
                self.assertEqual("failed", manager.store.record["status"])

    def test_source_keeps_mutation_and_execution_guards(self) -> None:
        source = (ROOT / "deploy/hermes-coders/codex_provider_chain_runner.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("self._fingerprint() != baseline", source)
        self.assertIn("primary_execution_started", source)
        self.assertIn('"execution_started": True', source)
        self.assertIn('"BYESU_HERMES_CODEX_API_KEY"', source)
        self.assertIn('"BYESU_HERMES_GPT_PRO_API_KEY"', source)


if __name__ == "__main__":
    unittest.main()
