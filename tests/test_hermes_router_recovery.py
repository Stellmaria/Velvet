from __future__ import annotations

import ast
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = "/srv/hermes-coders/releases/current-hermes-coders"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


source_guard = load_module(
    "hermes_runtime_source_guard_test_module",
    ROOT / "deploy/hermes-coders/runtime_source_guard.py",
)
tier_smoke = load_module(
    "hermes_tier_provider_smoke_test_module",
    ROOT / "deploy/hermes-coders/tier_provider_smoke.py",
)
router_smoke = load_module(
    "hermes_router_smoke_test_module",
    ROOT / "deploy/hermes-orchestration/router_smoke.py",
)


class HermesRouterRecoveryContractTests(unittest.TestCase):
    def test_coder_runtime_pulls_router_into_same_release_lifecycle(self) -> None:
        coders = (ROOT / "deploy/systemd/hermes-coders.service").read_text(
            encoding="utf-8"
        )
        router = (ROOT / "deploy/systemd/hermes-coder-router.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("Wants=network-online.target hermes-coder-router.service", coders)
        self.assertIn("PartOf=hermes-coders.service", router)
        self.assertIn(
            "After=docker.service hermes-operator-control.service hermes-coders.service",
            router,
        )
        self.assertIn(
            f"WorkingDirectory={RELEASE_ROOT}/deploy/hermes-orchestration",
            router,
        )
        self.assertIn(
            "ExecStartPost=/usr/bin/python3 "
            f"{RELEASE_ROOT}/deploy/hermes-orchestration/router_smoke.py",
            router,
        )
        self.assertIn(
            "ExecReload=/usr/bin/python3 "
            f"{RELEASE_ROOT}/deploy/hermes-orchestration/router_smoke.py",
            router,
        )
        self.assertNotIn("/srv/velvet/deploy/hermes-orchestration", router)

    def test_router_smoke_checks_tier_parity_without_printing_token(self) -> None:
        source = (ROOT / "deploy/hermes-orchestration/router_smoke.py").read_text(
            encoding="utf-8"
        )
        ast.parse(source)
        self.assertIn("/v1/coders/velvet/capabilities", source)
        self.assertIn("/v1/coders/max/capabilities", source)
        self.assertIn("routes_by_tier", source)
        self.assertIn("VELVET_MAX_PARITY_OK", source)
        self.assertIn("HERMES_CODER_ROUTER_CLIENT_TOKEN", source)
        self.assertIn("Path(__file__).resolve().parent", source)
        self.assertIn('"--project-name"', source)
        self.assertNotIn("print(token", source)
        self.assertNotIn("print(os.environ", source)
        self.assertTrue(Path(router_smoke._COMPOSE[-1]).is_absolute())

    def test_runtime_configures_same_provider_catalog_for_both_projects(self) -> None:
        source = (ROOT / "deploy/hermes-coders/compose.runtime.yaml").read_text(
            encoding="utf-8"
        )
        expected = (
            "CODEX_PROVIDER_FALLBACK_MODELS: "
            "gpt-5.4-mini,gpt-5.6-terra,gpt-5.6-luna"
        )
        self.assertEqual(2, source.count(expected))
        self.assertEqual(2, source.count("/app/codex_provider_chain_runner.py"))
        self.assertEqual(2, source.count("/app/codex_tier_runner.py"))
        self.assertEqual(2, source.count("/app/codex_launcher_runner.py"))
        self.assertEqual(4, source.count("/app/codex_context_launcher_runner.py"))
        self.assertIn("Actual order is selected from immutable requested_tier", source)
        self.assertNotIn("CODEX_PROVIDER_FALLBACK_MODEL:", source)

    def test_systemd_runs_runtime_and_tier_provider_smokes(self) -> None:
        unit = (ROOT / "deploy/systemd/hermes-coders.service").read_text(
            encoding="utf-8"
        )
        self.assertEqual(2, unit.count("/usr/bin/chmod 0644"))
        self.assertEqual(2, unit.count("runtime_source_guard.py"))
        self.assertEqual(4, unit.count("tier_provider_smoke.py"))
        self.assertEqual(2, unit.count("runtime_smoke.py"))
        self.assertIn(RELEASE_ROOT, unit)
        self.assertNotIn("/srv/velvet/deploy/hermes-coders", unit)
        for source in (
            "codex_delegate.py",
            "codex_first_runner.py",
            "codex_first_safe_runner.py",
            "codex_provider_chain_runner.py",
            "codex_tier_runner.py",
            "codex_launcher_runner.py",
            "codex_context_launcher_runner.py",
        ):
            self.assertEqual(2, unit.count(source), source)

    def test_runtime_source_guard_rejects_private_bind_mount(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in source_guard.RUNTIME_SOURCES:
                path = root / name
                path.write_text("test\n", encoding="utf-8")
                os.chmod(path, 0o644)
            source_guard.validate_runtime_sources(root)
            os.chmod(root / source_guard.RUNTIME_SOURCES[0], 0o600)
            with self.assertRaises(source_guard.RuntimeSourceError):
                source_guard.validate_runtime_sources(root)

    def test_tier_provider_smoke_accepts_mini_or_fail_closed(self) -> None:
        capabilities = {
            "routing": {
                "downgrade_allowed": False,
                "mutation_audit": {
                    "successful_runs": True,
                    "read_only_fail_closed": True,
                },
                "provider_fallback": {
                    "enabled": True,
                    "routes_by_tier": dict(tier_smoke._EXPECTED_ROUTES),
                    "after_mutation": False,
                    "after_execution_event": False,
                    "model_access_failure": "fail_closed",
                },
            }
        }
        payload = {
            "capabilities": capabilities,
            "availability": {
                "byesu-coder": {
                    "configured": True,
                    "models": {
                        "gpt-5.4-mini": False,
                        "gpt-5.6-terra": True,
                    },
                },
                "byesu-gpt-pro": {
                    "configured": True,
                    "models": {"gpt-5.6-luna": True},
                },
            },
        }
        self.assertEqual(
            "MINI_UNAVAILABLE_FAIL_CLOSED",
            tier_smoke.validate_payload("velvet", payload),
        )
        payload["availability"]["byesu-coder"]["models"]["gpt-5.4-mini"] = True
        self.assertEqual(
            "MINI_AVAILABLE",
            tier_smoke.validate_payload("velvet", payload),
        )
        capabilities["routing"]["provider_fallback"]["after_mutation"] = True
        with self.assertRaises(tier_smoke.TierProviderSmokeError):
            tier_smoke.validate_payload("velvet", payload)
        capabilities["routing"]["provider_fallback"]["after_mutation"] = False
        capabilities["routing"]["mutation_audit"]["read_only_fail_closed"] = False
        with self.assertRaises(tier_smoke.TierProviderSmokeError):
            tier_smoke.validate_payload("velvet", payload)


if __name__ == "__main__":
    unittest.main()
