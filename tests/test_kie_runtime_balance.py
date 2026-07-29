from __future__ import annotations

import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from velvet_bot.core.config.kie import load_kie_settings
from velvet_bot.domains.media_generation import KieModelCatalog
from velvet_bot.domains.media_generation.file_delivery_worker import _retry_delay
from velvet_bot.infrastructure.ai import KieClient, KieProtocolError
from velvet_bot.presentation.telegram.routers.workspace_meow_balance import (
    _render_balance,
    build_kie_balance_keyboard,
)


class KieRuntimeSettingsTests(unittest.TestCase):
    def test_runtime_defaults_are_four_workers_and_eleven_attempts(self) -> None:
        with patch.dict(
            os.environ,
            {
                "KIE_ENABLED": "false",
                "KIE_USD_TO_RUB": "0",
                "KIE_MAX_CONCURRENT_GENERATIONS": "4",
                "KIE_GENERATION_MAX_ATTEMPTS": "11",
            },
            clear=False,
        ):
            settings = load_kie_settings()

        self.assertEqual(4, settings.max_concurrent_generations)
        self.assertEqual(11, settings.generation_max_attempts)

    def test_retry_delay_is_bounded(self) -> None:
        self.assertEqual(1.0, _retry_delay(1))
        self.assertEqual(30.0, _retry_delay(11))


class KieAccountCreditsTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_account_credits_uses_common_api(self) -> None:
        calls: list[tuple[str, str]] = []

        def transport(method, url, headers, payload, timeout):
            calls.append((method, url))
            self.assertIsNone(payload)
            self.assertIn("Authorization", headers)
            return {"code": 200, "msg": "success", "data": 321.5}

        client = KieClient(
            api_key="secret",
            models=KieModelCatalog(),
            transport=transport,
        )

        credits = await client.get_account_credits()

        self.assertEqual(Decimal("321.5"), credits)
        self.assertEqual(
            [("GET", "https://api.kie.ai/api/v1/chat/credit")],
            calls,
        )

    async def test_get_account_credits_rejects_invalid_data(self) -> None:
        client = KieClient(
            api_key="secret",
            models=KieModelCatalog(),
            transport=lambda *args: {"code": 200, "data": "not-a-number"},
        )

        with self.assertRaises(KieProtocolError):
            await client.get_account_credits()


class KieBalancePresentationTests(unittest.TestCase):
    def test_balance_keyboard_has_refresh_and_back(self) -> None:
        keyboard = build_kie_balance_keyboard(workspace_id=7)
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertEqual(["Обновить баланс", "↩️ Мяу"], labels)

    def test_balance_text_separates_provider_credits_and_local_rubles(self) -> None:
        text = _render_balance(
            live_credits=Decimal("100"),
            balance_error=None,
            summary={
                "consumed_credits": Decimal("25"),
                "actual_cost_rub": Decimal("19.50"),
                "success_count": 2,
                "error_count": 1,
                "reserved_count": 1,
                "queued": 3,
                "running": 2,
            },
            recent=(
                {
                    "model_name": "grok_imagine_video",
                    "consumed_credits": Decimal("8"),
                    "actual_cost_rub": Decimal("4.80"),
                },
            ),
            concurrency=4,
            attempts=11,
        )

        self.assertIn("100 кредитов", text)
        self.assertIn("25 кредитов", text)
        self.assertIn("19,50 ₽", text)
        self.assertIn("2/4", text)
        self.assertIn("11", text)
        self.assertIn("Grok Imagine v1", text)


if __name__ == "__main__":
    unittest.main()
