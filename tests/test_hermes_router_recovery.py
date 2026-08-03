from __future__ import annotations

import ast
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
provider_smoke = load_module(
    "hermes_provider_chain_smoke_test_module",
    ROOT / "deploy/hermes-coders/provider_chain_smoke.py",
)


class HermesRouterRecoveryContractTests(unittest.TestCase):
    def test_coder_runtime_pulls_router_into_same_lifecycle(self) -> None:
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
            "ExecStartPost=/usr/bin/python3 /srv/velvet/deploy/hermes-orchestration/router_smoke.py",
            router,
        )
        self.assertIn(
            "ExecReload=/usr/bin/python3 /srv/velvet/deploy/hermes-orchestration/router_smoke.py",
            router,
        )

    def test_router_smoke_checks_both_projects_without_printing_token(self) -> None:
        source = (ROOT / "deploy/hermes-orchestration/router_smoke.py").read_text(
            encoding="utf-8"
        )
        ast.parse(source)
        self.assertIn('for project in ("velvet", "max")', source)
        self.assertIn("/v1/coders/{project}/capabilities", source)
        self.assertIn("HERMES_CODER_ROUTER_CLIENT_TOKEN", source)
        self.assertNotIn("print(token", source)
        self.assertNotIn("print(os.environ", source)
        self.assertIn('"docker", "compose", "-f", "compose.yaml"', source)

    def test_runtime_configures_full_provider_chain_for_both_projects(self) -> None:
        source = (ROOT / "deploy/hermes-coders/compose.runtime.yaml").read_text(
            encoding="utf-8"
        )
        expected = (
            "CODEX_PROVIDER_FALLBACK_MODELS: "
            "gpt-5.4-mini,gpt-5.6-terra,gpt-5.6-luna"
        )
        self.assertEqual(2, source.count(expected))
        self.assertEqual(4, source.count("/app/codex_provider_chain_runner.py"))
        self.assertNotIn("CODEX_PROVIDER_FALLBACK_MODEL:", source)

    def test_systemd_normalizes_and_verifies_bind_mount_permissions(self) -> None:
        unit = (ROOT / "deploy/systemd/hermes-coders.service").read_text(
            encoding="utf-8"
        )
        self.assertEqual(2, unit.count("/usr/bin/chmod 0644"))
        self.assertEqual(2, unit.count("runtime_source_guard.py"))
        self.assertEqual(2, unit.count("provider_chain_smoke.py"))
        for source in (
            "codex_delegate.py",
            "codex_first_runner.py",
            "codex_first_safe_runner.py",
            "codex_provider_chain_runner.py",
        ):
            self.assertEqual(2, unit.count(source), source)
        self.assertEqual(6, unit.count("compose.runtime.yaml"))

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

    def test_provider_chain_smoke_validates_safe_public_contract(self) -> None:
        payload = {
            "routing": {
                "primary_route": "codex_subscription",
                "provider_fallback": {
                    "enabled": True,
                    "route": "byesu_provider",
                    "model": "gpt-5.4-mini",
                    "models": [
                        "gpt-5.4-mini",
                        "gpt-5.6-terra",
                        "gpt-5.6-luna",
                    ],
                    "credential_groups": [
                        {
                            "name": "byesu-coder",
                            "models": ["gpt-5.4-mini", "gpt-5.6-terra"],
                        },
                        {"name": "byesu-gpt-pro", "models": ["gpt-5.6-luna"]},
                    ],
                    "after_mutation": False,
                },
            }
        }
        provider_smoke.validate_capabilities("velvet", payload)
        payload["routing"]["provider_fallback"]["after_mutation"] = True
        with self.assertRaises(provider_smoke.ProviderChainSmokeError):
            provider_smoke.validate_capabilities("velvet", payload)


if __name__ == "__main__":
    unittest.main()
