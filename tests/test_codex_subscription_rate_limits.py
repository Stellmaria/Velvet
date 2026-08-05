from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from velvet_bot.presentation.telegram.routers.workspace_auf_provider_balances import (
    CodexSubscriptionLimits,
    _codex_lines,
    _fetch_codex_subscription_limits,
)

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CodexSubscriptionRateLimitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_module(
            "codex_runner_rate_limit_test_module",
            ROOT / "deploy/hermes-coders/codex_runner.py",
        )
        cls.router_source = (
            ROOT / "deploy/hermes-operator/coder_router.py"
        ).read_text(encoding="utf-8")

    def test_runner_normalizes_plus_windows_without_identity(self) -> None:
        payload = self.runner.normalize_codex_subscription_rate_limits(
            {
                "account": {
                    "type": "chatgpt",
                    "email": "hidden@example.com",
                    "planType": "plus",
                }
            },
            {
                "rateLimits": {
                    "primary": {
                        "usedPercent": 27,
                        "windowDurationMins": 300,
                        "resetsAt": 1_800_000_000,
                    },
                    "secondary": {
                        "usedPercent": 61.5,
                        "windowDurationMins": 10_080,
                        "resetsAt": 1_800_500_000,
                    },
                    "rateLimitReachedType": None,
                }
            },
        )

        self.assertEqual("plus", payload["plan_type"])
        self.assertEqual(27.0, payload["primary"]["used_percent"])
        self.assertEqual(10_080, payload["secondary"]["window_duration_mins"])
        self.assertNotIn("account", payload)
        self.assertNotIn("email", repr(payload))

    def test_router_exposes_only_read_only_rate_limit_proxy(self) -> None:
        self.assertIn(
            'return self.upstream(self._target(project), "GET", "/v1/rate-limits")',
            self.router_source,
        )
        self.assertIn('parts[3] == "rate-limits"', self.router_source)

    def test_bot_formats_remaining_plus_limits(self) -> None:
        payload = {
            "plan_type": "plus",
            "primary": {
                "used_percent": 27,
                "window_duration_mins": 300,
                "resets_at": 1_800_000_000,
            },
            "secondary": {
                "used_percent": 61.5,
                "window_duration_mins": 10_080,
                "resets_at": 1_800_500_000,
            },
        }
        with (
            patch.dict(
                os.environ,
                {
                    "CODEX_LIMITS_BASE_URL": "http://hermes-coder-router:8878",
                    "CODEX_LIMITS_API_KEY": "router-secret-not-printed",
                },
                clear=True,
            ),
            patch(
                "velvet_bot.presentation.telegram.routers."
                "workspace_auf_provider_balances._read_codex_limits_json",
                return_value=payload,
            ),
        ):
            limits = asyncio.run(_fetch_codex_subscription_limits())

        lines = _codex_lines(
            limits,
            now=datetime.fromtimestamp(1_799_990_000, timezone.utc),
        )
        self.assertEqual(2, len(lines))
        self.assertIn("Codex Plus · 5 ч", lines[0])
        self.assertIn("73% осталось", lines[0])
        self.assertIn("Codex Plus · 7 дн.", lines[1])
        self.assertIn("38.5% осталось", lines[1])
        self.assertNotIn("router-secret", "\n".join(lines))

    def test_bot_reports_missing_integration_safely(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            limits = asyncio.run(_fetch_codex_subscription_limits())
        self.assertIsInstance(limits, CodexSubscriptionLimits)
        self.assertEqual("интеграция не настроена", limits.error)


if __name__ == "__main__":
    unittest.main()
