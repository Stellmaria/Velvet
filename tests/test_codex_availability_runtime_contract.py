from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODERS = ROOT / "deploy" / "hermes-coders"


class CodexAvailabilityRuntimeContractTests(unittest.TestCase):
    def test_coder_provider_chain_is_gated_by_persisted_dynamic_flag(self) -> None:
        context = (CODERS / "codex_context_launcher_runner.py").read_text(
            encoding="utf-8"
        )
        provider = (CODERS / "codex_provider_chain_runner.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "return not self.codex_availability.codex_available",
            context,
        )
        self.assertIn("if self._cooling_down():", provider)
        self.assertLess(
            provider.index("if self._cooling_down():"),
            provider.index("primary_models = tuple("),
        )
        self.assertIn("self.codex_availability.note_subscription_failure", context)

    def test_image_gate_uses_the_same_manager_state(self) -> None:
        context = (CODERS / "codex_context_launcher_runner.py").read_text(
            encoding="utf-8"
        )
        image_gate = (CODERS / "codex_image_limit_preflight.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("self.codex_availability = CodexAvailabilityGate", context)
        self.assertIn('gate = getattr(self, "codex_availability", None)', image_gate)
        self.assertIn('state.get("codex_available") is not True', image_gate)
        self.assertNotIn("read_codex_subscription_rate_limits", image_gate)

    def test_periodic_live_check_is_exactly_five_hours_for_both_projects(self) -> None:
        compose = (CODERS / "compose.runtime.yaml").read_text(encoding="utf-8")
        availability = (CODERS / "codex_availability.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("DEFAULT_REFRESH_SECONDS = 5 * 60 * 60", availability)
        self.assertEqual(
            2,
            compose.count('CODEX_AVAILABILITY_REFRESH_SECONDS: "18000"'),
        )
        self.assertIn('source="periodic_5h"', availability)
        self.assertIn('source="provider_reset_at"', availability)

    def test_operator_cli_can_read_refresh_hold_and_clear_without_restart(self) -> None:
        cli = (CODERS / "codex_availability_ctl.py").read_text(encoding="utf-8")
        for command in ("status", "refresh", "hold", "clear"):
            self.assertIn(f'commands.add_parser("{command}")', cli)
        self.assertIn('hold.add_argument(\n        "--until"', cli)
        self.assertIn('gate.hold(args.until)', cli)
        self.assertIn('gate.clear()', cli)

    def test_obsolete_per_request_image_probe_is_not_projected(self) -> None:
        projection = (CODERS / "compose_image_runtime_env.py").read_text(
            encoding="utf-8"
        )
        compose = (CODERS / "compose.runtime.yaml").read_text(encoding="utf-8")
        self.assertNotIn("CODEX_IMAGE_LIMIT_PREFLIGHT_TIMEOUT_SECONDS", projection)
        self.assertNotIn("CODEX_IMAGE_LIMIT_PREFLIGHT_ENABLED", projection)
        self.assertNotIn("CODEX_IMAGE_LIMIT_PREFLIGHT_ENABLED:", compose)


if __name__ == "__main__":
    unittest.main()
