from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODERS = ROOT / "deploy" / "hermes-coders"
if str(CODERS) not in sys.path:
    sys.path.insert(0, str(CODERS))

import byesu_image_routing_policy as routing  # noqa: E402
import codex_image_limit_preflight as preflight  # noqa: E402


class CodexImageLimitPreflightTests(unittest.TestCase):
    def test_reached_type_is_exhausted(self) -> None:
        self.assertTrue(
            preflight.codex_limit_exhausted(
                {
                    "rate_limit_reached_type": "secondary",
                    "primary": {"used_percent": 20, "resets_at": 2_000},
                },
                now_epoch=1_000,
            )
        )

    def test_active_hundred_percent_window_is_exhausted(self) -> None:
        self.assertTrue(
            preflight.codex_limit_exhausted(
                {
                    "rate_limit_reached_type": None,
                    "secondary": {
                        "used_percent": 100,
                        "resets_at": 2_000,
                    },
                },
                now_epoch=1_000,
            )
        )

    def test_expired_hundred_percent_window_is_available(self) -> None:
        self.assertFalse(
            preflight.codex_limit_exhausted(
                {
                    "rate_limit_reached_type": None,
                    "secondary": {
                        "used_percent": 100,
                        "resets_at": 900,
                    },
                },
                now_epoch=1_000,
            )
        )

    def test_ninety_nine_percent_still_uses_codex(self) -> None:
        self.assertFalse(
            preflight.codex_limit_exhausted(
                {
                    "rate_limit_reached_type": None,
                    "primary": {
                        "used_percent": 99,
                        "resets_at": 2_000,
                    },
                    "secondary": {
                        "used_percent": 99.9,
                        "resets_at": 3_000,
                    },
                },
                now_epoch=1_000,
            )
        )

    def test_missing_or_unknown_snapshot_does_not_invent_limit(self) -> None:
        self.assertFalse(preflight.codex_limit_exhausted(None, now_epoch=1_000))
        self.assertFalse(preflight.codex_limit_exhausted({}, now_epoch=1_000))
        self.assertFalse(
            preflight.codex_limit_exhausted(
                {"rate_limit_reached_type": "not_reached"},
                now_epoch=1_000,
            )
        )

    def test_every_supported_quality_uses_same_codex_primary_gate(self) -> None:
        for resolution in ("1K", "2K", "4K"):
            self.assertTrue(routing.uses_codex_primary(resolution), resolution)

    def test_image_routing_reads_dynamic_flag_not_live_rate_limits(self) -> None:
        source = (
            CODERS / "codex_image_limit_preflight.py"
        ).read_text(encoding="utf-8")
        self.assertIn('state = gate.status()', source)
        self.assertIn('state.get("codex_available") is not True', source)
        self.assertNotIn("read_codex_subscription_rate_limits", source)
        self.assertIn("gate.note_subscription_failure", source)

    def test_runtime_install_order_is_routing_then_gate_then_high_res(self) -> None:
        source = (
            CODERS / "codex_context_launcher_runner.py"
        ).read_text(encoding="utf-8")
        routing_index = source.index("install_byesu_image_routing_policy()")
        gate_index = source.index("install_codex_image_limit_preflight()")
        high_res_index = source.index("install_codex_image_high_res_export()")
        self.assertLess(routing_index, gate_index)
        self.assertLess(gate_index, high_res_index)


if __name__ == "__main__":
    unittest.main()
