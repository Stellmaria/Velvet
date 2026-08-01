from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from velvet_bot.app.auf_reference_privacy_install import (
    _load_reference_source_options,
    _reference_summary,
)
from velvet_bot.domains.auf_wallet.pricing import (
    format_owner_price_details,
    quote_auf_payload,
)


class _PriceConnection:
    def __init__(self, row, *, package_floor=Decimal("2")) -> None:
        self.row = row
        self.package_floor = package_floor

    async def fetchrow(self, query, *args):
        if "FROM auf_price_versions" in query:
            return self.row
        if "FROM auf_economy_settings" in query:
            return {
                "retail_auf_usd": Decimal("0.03"),
                "billing_usd_to_rub": Decimal("80"),
                "billing_usd_to_byn": Decimal("3"),
                "retail_markup_percent": Decimal("30"),
            }
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        if "FROM auf_package_prices" in query:
            return self.package_floor
        if "FROM auf_user_markup_overrides" in query:
            return None
        raise AssertionError(query)


class AufRetailPricingTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _payload(
        *,
        model: str,
        resolution: str,
        duration: int = 6,
        references: int = 0,
        audio: bool = False,
    ) -> dict[str, object]:
        return {
            "workspace_id": 1,
            "user_id": 100,
            "request": {
                "model": model,
                "resolution": resolution,
                "duration_seconds": duration,
                "references": [{} for _ in range(references)],
                "extra_input": {"generate_audio": audio},
            },
        }

    async def test_fixed_price_uses_extra_reference_cost_and_whole_velvets(self) -> None:
        connection = _PriceConnection(
            {
                "id": 1,
                "version_key": "retail:test:seedream",
                "provider": "kie",
                "model_alias": "seedream_5_pro",
                "resolution": "2K",
                "audio": None,
                "pricing_basis": "fixed",
                "unit_cost_usd": Decimal("0.15"),
                "extra_reference_cost_usd": Decimal("0.005"),
            }
        )
        quote = await quote_auf_payload(
            connection,
            self._payload(
                model="seedream_5_pro",
                resolution="2K",
                references=5,
            ),
        )
        self.assertEqual(Decimal("0.170"), quote.provider_cost_usd)
        self.assertEqual(Decimal("0.2210"), quote.target_retail_usd)
        self.assertEqual(90_000, quote.quoted_units)
        self.assertEqual(0, quote.quoted_units % 10_000)

    async def test_per_second_audio_price_is_selected(self) -> None:
        connection = _PriceConnection(
            {
                "id": 2,
                "version_key": "retail:test:seedance-audio",
                "provider": "kie",
                "model_alias": "seedance_15_pro_video",
                "resolution": "720p",
                "audio": True,
                "pricing_basis": "per_second",
                "unit_cost_usd": Decimal("0.037"),
                "extra_reference_cost_usd": Decimal("0"),
            }
        )
        quote = await quote_auf_payload(
            connection,
            self._payload(
                model="seedance_15_pro_video",
                resolution="720p",
                duration=5,
                references=3,
                audio=True,
            ),
        )
        self.assertEqual(Decimal("0.185"), quote.provider_cost_usd)
        self.assertEqual(Decimal("0.2405"), quote.target_retail_usd)
        self.assertEqual(100_000, quote.quoted_units)
        self.assertEqual(0, quote.quoted_units % 10_000)

    async def test_owner_breakdown_contains_only_provider_cost_in_three_currencies(self) -> None:
        connection = _PriceConnection(
            {
                "id": 3,
                "version_key": "retail:test:owner",
                "provider": "private-provider",
                "model_alias": "nano_banana_2",
                "resolution": "1K",
                "audio": None,
                "pricing_basis": "fixed",
                "unit_cost_usd": Decimal("0.02"),
                "extra_reference_cost_usd": Decimal("0"),
            }
        )
        quote = await quote_auf_payload(
            connection,
            self._payload(model="nano_banana_2", resolution="1K"),
        )
        text = format_owner_price_details(quote)
        self.assertIn("PRIVATE-PROVIDER", text)
        self.assertIn("$", text)
        self.assertIn("₽ РФ", text)
        self.assertIn("Br", text)
        self.assertIn("только Стэл", text)
        for forbidden in (
            "VL",
            "вельвет",
            "Наценка",
            "Выручка",
            "Прибыль",
            "маржа",
            "Списание",
        ):
            self.assertNotIn(forbidden, text)


class AufReferencePrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_system_sources_are_requested_only_for_global_owner(self) -> None:
        class _Connection:
            def __init__(self) -> None:
                self.include_system = None

            async def fetch(self, query, user_id, workspace_id, include_system):
                self.include_system = include_system
                return []

        class _Acquire:
            def __init__(self, connection) -> None:
                self.connection = connection

            async def __aenter__(self):
                return self.connection

            async def __aexit__(self, exc_type, exc, traceback):
                return False

        class _Database:
            def __init__(self) -> None:
                self.connection = _Connection()

            def acquire(self):
                return _Acquire(self.connection)

        owner_database = _Database()
        await _load_reference_source_options(
            owner_database,
            user_id=1,
            workspace_id=2,
            include_system=True,
        )
        self.assertTrue(owner_database.connection.include_system)

        user_database = _Database()
        await _load_reference_source_options(
            user_database,
            user_id=1,
            workspace_id=2,
            include_system=False,
        )
        self.assertFalse(user_database.connection.include_system)

    def test_public_reference_summary_does_not_expose_system_archive(self) -> None:
        references = (
            SimpleNamespace(source="upload"),
            SimpleNamespace(source="system"),
            SimpleNamespace(source="personal"),
        )
        public = _reference_summary(references, global_owner=False)
        owner = _reference_summary(references, global_owner=True)
        self.assertNotIn("систем", public.casefold())
        self.assertIn("систем", owner.casefold())

    def test_migration_creates_user_registry_without_content_columns(self) -> None:
        migration = Path("migrations/z025_auf_retail_user_registry.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS telegram_users", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS telegram_user_events", migration)
        self.assertNotIn("message_text", migration)
        self.assertNotIn("prompt_text", migration)
        self.assertNotIn("telegram_file_id", migration)


if __name__ == "__main__":
    unittest.main()
