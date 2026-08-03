from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


if __name__ == "__main__":
    unittest.main()
