from __future__ import annotations

import inspect
import unittest
from decimal import Decimal
from pathlib import Path

from velvet_bot.app import auf_reference_privacy_install as privacy
from velvet_bot.domains.auf_wallet.pricing import quote_auf_payload
from velvet_bot.domains.user_registry import TelegramUserRepository
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.presentation.telegram.middleware.user_activity import (
    _callback_metadata,
    _command_name,
)
from velvet_bot.presentation.telegram.routers import user_management
from velvet_bot.presentation.telegram.routers import workspace_auf_wallet


class _PriceConnection:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self.calls = 0

    async def fetchrow(self, query: str, *args):
        self.calls += 1
        if "FROM auf_price_versions" in query:
            return self.row
        raise AssertionError("Retail quote must not read provider_auf_usd")


class AufRetailPricingTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _payload(
        *,
        model: str,
        resolution: str,
        duration: int = 6,
        references: int = 1,
        audio: bool = False,
    ) -> dict[str, object]:
        return {
            "request": {
                "model": model,
                "resolution": resolution,
                "duration_seconds": duration,
                "references": [{} for _ in range(references)],
                "extra_input": {"generate_audio": audio},
            }
        }

    async def test_fixed_retail_price_is_separate_from_provider_cost(self) -> None:
        connection = _PriceConnection(
            {
                "id": 1,
                "version_key": "retail:test",
                "provider": "internal",
                "model_alias": "nano_banana_2",
                "resolution": "2K",
                "audio": None,
                "pricing_basis": "fixed",
                "unit_cost_usd": Decimal("0.02"),
                "extra_reference_cost_usd": Decimal("0"),
                "retail_units": 50_000,
                "extra_reference_retail_units": 0,
            }
        )
        quote = await quote_auf_payload(
            connection,
            self._payload(model="nano_banana_2", resolution="2K"),
        )
        self.assertEqual(Decimal("0.02"), quote.provider_cost_usd)
        self.assertEqual(50_000, quote.quoted_units)
        self.assertEqual(1, connection.calls)

    async def test_per_second_and_extra_reference_retail_prices(self) -> None:
        connection = _PriceConnection(
            {
                "id": 2,
                "version_key": "retail:test:seconds",
                "provider": "internal",
                "model_alias": "seedance_15_pro_video",
                "resolution": "720p",
                "audio": True,
                "pricing_basis": "per_second",
                "unit_cost_usd": Decimal("0.035"),
                "extra_reference_cost_usd": Decimal("0.005"),
                "retail_units": 25_000,
                "extra_reference_retail_units": 5_000,
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
        self.assertEqual(135_000, quote.quoted_units)


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

        ordinary = _Database()
        await privacy._load_private_sources(
            ordinary,
            user_id=123,
            active_workspace_id=55,
        )
        self.assertFalse(ordinary.connection.include_system)

        owner = _Database()
        await privacy._load_private_sources(
            owner,
            user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            active_workspace_id=55,
        )
        self.assertTrue(owner.connection.include_system)

    def test_public_reference_summary_does_not_expose_system_archive(self) -> None:
        text = privacy._private_review_text("prompt", ())
        self.assertIn("из базы", text)
        self.assertNotIn("системный архив", text.casefold())
        self.assertNotIn("личное пространство", text.casefold())


class UserObservabilityContractTests(unittest.TestCase):
    def test_command_and_callback_metadata_are_content_free(self) -> None:
        self.assertEqual("velvet_grant", _command_name("/velvet_grant @user 100 secret"))
        action, module, workspace_id = _callback_metadata(
            "auf:photo_generate:42:provider-secret:9:0"
        )
        self.assertEqual("photo_generate", action)
        self.assertEqual("auf", module)
        self.assertEqual(42, workspace_id)

    def test_grant_amount_uses_exact_decimal_units(self) -> None:
        self.assertEqual(Decimal("12.3456"), user_management._positive_amount("12,3456"))
        self.assertIsNone(user_management._positive_amount("0"))
        self.assertIsNone(user_management._positive_amount("1.00001"))

    def test_public_wallet_source_hides_internal_costs(self) -> None:
        source = inspect.getsource(workspace_auf_wallet._render_wallet)
        self.assertIn("if global_owner", source)
        self.assertNotIn("1 Ауф покрывает", source)
        self.assertNotIn("Дополнительная наценка", source)
        self.assertIn(
            "Стэл получила уведомление",
            inspect.getsource(workspace_auf_wallet.handle_auf_wallet_action),
        )

    def test_registry_contract_does_not_accept_content_fields(self) -> None:
        migration = Path("migrations/z025_auf_retail_user_registry.sql").read_text(
            encoding="utf-8"
        )
        parameters = set(inspect.signature(TelegramUserRepository.observe).parameters)
        for forbidden in ("message_text", "prompt", "file_id", "callback_data"):
            self.assertNotIn(forbidden, migration)
            self.assertNotIn(forbidden, parameters)
        self.assertIn("first_seen_at", migration)
        self.assertIn("last_seen_at", migration)
        self.assertIn("command_count", migration)

    def test_approved_retail_catalog_is_versioned(self) -> None:
        migration = Path("migrations/z025_auf_retail_user_registry.sql").read_text(
            encoding="utf-8"
        )
        expected_rows = (
            "'2026-07-30:retail:nano-banana-2:1k'",
            "0.02000000, 0, 40000",
            "'2026-07-30:retail:nano-banana-pro:4k'",
            "0.03000000, 0, 110000",
            "'2026-07-30:retail:seedream-5-pro:2k'",
            "0.15000000, 0.00500000, 90000, 5000",
            "(2500,5490.00",
        )
        for expected in expected_rows:
            self.assertIn(expected, migration)


if __name__ == "__main__":
    unittest.main()
