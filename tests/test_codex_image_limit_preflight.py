from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CODERS = ROOT / "deploy" / "hermes-coders"
if str(CODERS) not in sys.path:
    sys.path.insert(0, str(CODERS))

import codex_image_limit_preflight as preflight  # noqa: E402


class CodexImageLimitPreflightTests(unittest.TestCase):
    def test_reached_type_skips_codex(self) -> None:
        self.assertTrue(
            preflight.codex_limit_exhausted(
                {
                    "rate_limit_reached_type": "secondary",
                    "primary": {"used_percent": 20, "resets_at": 2_000},
                },
                now_epoch=1_000,
            )
        )

    def test_active_hundred_percent_window_skips_codex(self) -> None:
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

    def test_expired_hundred_percent_window_fails_open(self) -> None:
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

    def test_missing_or_unknown_snapshot_fails_open(self) -> None:
        self.assertFalse(preflight.codex_limit_exhausted(None, now_epoch=1_000))
        self.assertFalse(preflight.codex_limit_exhausted({}, now_epoch=1_000))
        self.assertFalse(
            preflight.codex_limit_exhausted(
                {"rate_limit_reached_type": "not_reached"},
                now_epoch=1_000,
            )
        )

    def test_probe_failure_returns_none(self) -> None:
        manager = type(
            "Manager",
            (),
            {"codex_bin": "codex", "codex_home": Path("/tmp/codex")},
        )()
        with patch.object(
            preflight,
            "read_codex_subscription_rate_limits",
            side_effect=RuntimeError("probe unavailable"),
        ):
            self.assertIsNone(preflight._fresh_snapshot(manager))

    def test_runtime_installs_preflight_after_parameter_routing(self) -> None:
        source = (
            CODERS / "codex_context_launcher_runner.py"
        ).read_text(encoding="utf-8")
        routing = source.index("install_byesu_image_routing_policy()")
        limit = source.index("install_codex_image_limit_preflight()")
        self.assertLess(routing, limit)


if __name__ == "__main__":
    unittest.main()
