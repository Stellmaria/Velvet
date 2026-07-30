from __future__ import annotations

import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from velvet_bot.core.config.kie import load_kie_settings
from velvet_bot.domains.media_generation import KieModelCatalog
from velvet_bot.domains.media_generation.file_delivery_worker import _retry_delay
from velvet_bot.infrastructure.ai import KieClient, KieProtocolError
from velvet_bot.presentation.telegram.routers.workspace_auf_balance import (
    DailyNbrbExchangeRateService,
    NbrbRateClient,
    NbrbRateError,
    NbrbRateSnapshot,
    _render_balance,
    build_kie_balance_keyboard,
)


def _nbrb_rates(
    *,
    usd_date: str = "2026-07-29",
    rub_date: str = "2026-07-29",
):
    return [
        {
            "Cur_Abbreviation": "USD",
            "Cur_Scale": 1,
            "Cur_OfficialRate": 2.8876,
            "Date": f"{usd_date}T00:00:00",
        },
        {
            "Cur_Abbreviation": "RUB",
            "Cur_Scale": 100,
            "Cur_OfficialRate": 3.6865,
            "Date": f"{rub_date}T00:00:00",
        },
    ]


class KieRuntimeSettingsTests(unittest.TestCase):
    def test_runtime_defaults_are_four_workers_and_eleven_attempts(self) -> None:
        with patch.dict(
            os.environ,
            {
                "KIE_ENABLED": "false",
                "KIE_USD_TO_RUB": "0",
                "KIE_CREDIT_USD": "0.005",
                "KIE_CREDIT_BYN": "0.019",
                "KIE_MAX_CONCURRENT_GENERATIONS": "4",
                "KIE_GENERATION_MAX_ATTEMPTS": "11",
            },
            clear=False,
        ):
            settings = load_kie_settings()

        self.assertEqual(4, settings.max_concurrent_generations)
        self.assertEqual(11, settings.generation_max_attempts)
        self.assertEqual(Decimal("0.005"), settings.credit_usd)
        self.assertEqual(Decimal("0.019"), settings.credit_byn)

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
        self.assertEqual(["Обновить баланс", "↩️ Ауф"], labels)

    def test_balance_text_converts_provider_credits_to_three_currencies(self) -> None:
        text = _render_balance(
            live_credits=Decimal("100"),
            balance_error=None,
            summary={
                "consumed_credits": Decimal("25"),
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
                },
            ),
            credit_usd=Decimal("0.005"),
            credit_byn=Decimal("0.019"),
            usd_to_rub=Decimal("78.0172"),
            concurrency=4,
            attempts=11,
        )

        self.assertIn("100 кредитов", text)
        self.assertIn("0,50 $ · 39,01 ₽ · 1,90 BYN", text)
        self.assertIn("25 кредитов", text)
        self.assertIn("0,125 $ · 9,75 ₽ · 0,475 BYN", text)
        self.assertIn("8 кр.</b> · 0,04 $ · 3,12 ₽ · 0,152 BYN", text)
        self.assertIn("1 кредит = 0,005 $ · 0,39 ₽ · 0,019 BYN", text)
        self.assertIn("2/4", text)
        self.assertIn("11", text)
        self.assertIn("Grok Imagine v1", text)


class NbrbRateClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_official_cross_rate_using_currency_scale(self) -> None:
        calls: list[tuple[str, int]] = []

        def transport(url: str, timeout_seconds: int):
            calls.append((url, timeout_seconds))
            return _nbrb_rates()

        client = NbrbRateClient(transport=transport, timeout_seconds=17)
        snapshot = await client.fetch(on_date=date(2026, 7, 29))

        self.assertEqual(date(2026, 7, 29), snapshot.effective_date)
        self.assertEqual(Decimal("2.8876"), snapshot.usd_to_byn)
        self.assertEqual(Decimal("0.036865"), snapshot.rub_to_byn)
        self.assertEqual(
            Decimal("2.8876") / Decimal("0.036865"),
            snapshot.usd_to_rub,
        )
        self.assertEqual(1, len(calls))
        self.assertIn("ondate=2026-07-29", calls[0][0])
        self.assertIn("periodicity=0", calls[0][0])
        self.assertEqual(17, calls[0][1])

    async def test_rejects_rates_from_different_effective_dates(self) -> None:
        client = NbrbRateClient(
            transport=lambda *_: _nbrb_rates(rub_date="2026-07-28")
        )

        with self.assertRaises(NbrbRateError):
            await client.fetch(on_date=date(2026, 7, 29))


class _NbrbRepository:
    def __init__(self) -> None:
        self.claimed = False
        self.successes: list[NbrbRateSnapshot] = []
        self.errors: list[BaseException] = []

    async def latest_success(self):
        return None

    async def claim_daily_attempt(self, check_date):
        if self.claimed:
            return False
        self.claimed = True
        return True

    async def mark_success(self, *, check_date, snapshot):
        self.successes.append(snapshot)

    async def mark_error(self, *, check_date, error):
        self.errors.append(error)


class DailyNbrbExchangeRateServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_calls_provider_only_once_for_the_calendar_day(self) -> None:
        repository = _NbrbRepository()
        provider_calls = 0

        def transport(*_):
            nonlocal provider_calls
            provider_calls += 1
            return _nbrb_rates()

        applied: list[Decimal] = []
        service = DailyNbrbExchangeRateService(
            repository=repository,  # type: ignore[arg-type]
            client=NbrbRateClient(transport=transport),
            timezone_name="Europe/Minsk",
            on_rate=applied.append,
        )

        self.assertEqual(1, await service.process_once())
        self.assertEqual(0, await service.process_once())
        self.assertEqual(1, provider_calls)
        self.assertEqual(1, len(repository.successes))
        self.assertEqual([], repository.errors)
        self.assertEqual(
            [Decimal("2.8876") / Decimal("0.036865")],
            applied,
        )


if __name__ == "__main__":
    unittest.main()
