from __future__ import annotations

import inspect
import unittest
from decimal import Decimal
from pathlib import Path

from velvet_bot.app import auf_owner_pricing_ui_install as pricing_ui
from velvet_bot.app import auf_photo_model_modes, composition
from velvet_bot.domains.auf_wallet.models import AUF_SCALE, format_vl_units
from velvet_bot.domains.auf_wallet.pricing import quote_auf_payload
from velvet_bot.presentation.telegram.routers import user_management


class _Connection:
    def __init__(self, *, override: Decimal | None, quality_surcharge: int) -> None:
        self.override = override
        self.quality_surcharge = quality_surcharge

    async def fetchrow(self, query: str, *args):
        if "FROM auf_price_versions" in query:
            return {
                "id": 1,
                "version_key": "policy:test",
                "provider": "grs",
                "model_alias": "nano_banana_2",
                "resolution": "2K",
                "audio": None,
                "pricing_basis": "fixed",
                "unit_cost_usd": Decimal("0.02"),
                "extra_reference_cost_usd": Decimal("0"),
                "quality_surcharge_velvets": self.quality_surcharge,
            }
        if "FROM auf_economy_settings" in query:
            return {
                "retail_auf_usd": Decimal("0.03"),
                "billing_usd_to_rub": Decimal("80"),
                "billing_usd_to_byn": Decimal("3"),
                "retail_markup_percent": Decimal("30"),
            }
        raise AssertionError(query)

    async def fetchval(self, query: str, *args):
        if "FROM auf_user_markup_overrides" in query:
            return self.override
        if "FROM auf_package_prices" in query:
            return Decimal("2")
        raise AssertionError(query)


class AufIndividualPricingPolicyTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _payload() -> dict[str, object]:
        return {
            "user_id": 55,
            "request": {
                "model": "nano_banana_2",
                "resolution": "2K",
                "duration_seconds": 6,
                "references": [{}],
                "extra_input": {},
            },
        }

    async def test_global_thirty_percent_uses_fixed_banana_quality_grid(self) -> None:
        quote = await quote_auf_payload(
            _Connection(override=None, quality_surcharge=1),
            self._payload(),
        )
        self.assertEqual(Decimal("30"), quote.markup_percent)
        self.assertEqual(1, quote.quality_surcharge_velvets)
        self.assertEqual(2 * AUF_SCALE, quote.quoted_units)

    async def test_individual_markup_replaces_global_percent(self) -> None:
        quote = await quote_auf_payload(
            _Connection(override=Decimal("0"), quality_surcharge=1),
            self._payload(),
        )
        self.assertEqual(Decimal("0.00"), quote.markup_percent)
        self.assertEqual(Decimal("0.00"), quote.user_markup_override_percent)
        self.assertEqual(2 * AUF_SCALE, quote.quoted_units)


class AufPricingPolicyContractTests(unittest.TestCase):
    def test_vl_formatter_accepts_only_whole_velvets(self) -> None:
        self.assertEqual("7 VL", format_vl_units(7 * AUF_SCALE))
        with self.assertRaises(ValueError):
            format_vl_units(AUF_SCALE + 1)

    def test_admin_markup_parser(self) -> None:
        self.assertEqual(Decimal("45.25"), user_management._markup_percent("45,25"))
        self.assertEqual(Decimal("0.00"), user_management._markup_percent("0"))
        self.assertIsNone(user_management._markup_percent("1000.01"))
        self.assertIsNone(user_management._markup_percent("nan"))

    def test_migration_sets_global_policy_and_banana_quality_steps(self) -> None:
        migration = Path(
            "migrations/z028_auf_individual_markup_and_quality.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("retail_markup_percent = 30.0000", migration)
        self.assertIn("auf_user_markup_overrides", migration)
        self.assertIn("WHEN '2K' THEN 1", migration)
        self.assertIn("WHEN '4K' THEN 2", migration)
        self.assertIn("quality_surcharge_velvets", migration)

    def test_model_first_is_wrapped_by_approved_pricing_policy(self) -> None:
        stages = composition._FEATURE_STAGE_NAMES
        self.assertLess(
            stages.index("install_auf_photo_model_modes"),
            stages.index("install_auf_owner_pricing_ui"),
        )
        source = inspect.getsource(auf_photo_model_modes)
        self.assertEqual(2, source.count("await photo_ui._show_auf_final("))

    def test_seedream_warning_and_grok_15_removal_are_installed(self) -> None:
        source = inspect.getsource(pricing_ui)
        self.assertIn("Чем больше референсов", source)
        self.assertIn('mapping.pop("grok15", None)', source)
        self.assertIn("Grok 1.5 удалён", source)
        self.assertNotIn("Grok 1.5 · качество", source)


if __name__ == "__main__":
    unittest.main()
