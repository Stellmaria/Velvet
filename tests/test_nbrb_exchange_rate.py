from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from velvet_bot.services.nbrb_exchange_rate import (
    DailyNbrbExchangeRateService,
    NbrbRateClient,
    NbrbRateError,
    NbrbRateSnapshot,
)


def _rates(*, usd_date: str = "2026-07-29", rub_date: str = "2026-07-29"):
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


class NbrbRateClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_official_cross_rate_using_currency_scale(self) -> None:
        calls: list[tuple[str, int]] = []

        def transport(url: str, timeout_seconds: int):
            calls.append((url, timeout_seconds))
            return _rates()

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
            transport=lambda *_: _rates(rub_date="2026-07-28")
        )

        with self.assertRaises(NbrbRateError):
            await client.fetch(on_date=date(2026, 7, 29))


class _Repository:
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
        repository = _Repository()
        provider_calls = 0

        def transport(*_):
            nonlocal provider_calls
            provider_calls += 1
            return _rates()

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
