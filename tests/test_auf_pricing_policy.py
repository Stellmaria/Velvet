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
    def __init__(
        self,
        *,
        model_alias: str = "nano_banana_2",
        resolution: str = "2K",
        unit_cost_usd: Decimal = Decimal("0.02"),
        override: Decimal | None = None,
        quality_surcharge: int = 1,
        minimum_velvets: int = 2,
    ) -> None:
        self.model_alias = model_alias
        self.resolution = resolution
        self.unit_cost_usd = unit_cost_usd
        self.override = override
        self.quality_surcharge = quality_surcharge
        self.minimum_velvets = minimum_velvets

    async def fetchrow(self, query: str, *args):
        if "FROM auf_price_versions" in query:
            return {
                "id": 1,
                "version_key": "policy:test",
                "provider": "grs",
                "model_alias": self.model_alias,
                "resolution": self.resolution,
                "audio": None,
                "pricing_basis": "fixed",
                "unit_cost_usd": self.unit_cost_usd,
                "extra_reference_cost_usd": Decimal("0"),
                "quality_surcharge_velvets": self.quality_surcharge,
                "minimum_velvets": self.minimum_velvets,
            }
        if "FROM auf_economy_settings" in query:
            return {
                "retail_auf_usd": Decimal("0.04309777"),
                "billing_usd_to_rub": Decimal("79.7257"),
                "billing_usd_to_byn": Decimal("3"),
                "retail_markup_percent": Decimal("42.86"),
                "quote_rub_per_vl": Decimal("4"),
                "operational_cost_buffer_percent": Decimal("5"),
                "minimum_user_markup_percent": Decimal("15"),
            }
        raise AssertionError(query)

    async def fetchval(self, query: str, *args):
        if "FROM auf_user_markup_overrides" in query:
            return self.override
        if "FROM auf_package_prices" in query:
            raise AssertionError("Generation quotes must not depend on package prices")
        raise AssertionError(query)


class AufIndividualPricingPolicyTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _payload(*, model: str = "nano_banana_2", resolution: str = "2K") -> dict[str, object]:
        return {
            "user_id": 55,
            "request": {
                "model": model,
                "resolution": resolution,
                "duration_seconds": 6,
                "references": [{}],
                "extra_input": {},
            },
        }

    async def test_global_policy_uses_stable_quote_reference(self) -> None:
        quote = await quote_auf_payload(
            _Connection(override=None, quality_surcharge=1, minimum_velvets=2),
            self._payload(),
        )
        self.assertEqual(Decimal("42.86"), quote.markup_percent)
        self.assertEqual(Decimal("4"), quote.quote_rub_per_vl)
        self.assertEqual(Decimal("5.00"), quote.operational_cost_buffer_percent)
        self.assertEqual(2 * AUF_SCALE, quote.quoted_units)

    async def test_individual_markup_is_floored_at_fifteen_percent(self) -> None:
        quote = await quote_auf_payload(
            _Connection(
                override=Decimal("0"),
                quality_surcharge=1,
                minimum_velvets=2,
            ),
            self._payload(),
        )
        self.assertEqual(Decimal("0.00"), quote.user_markup_override_percent)
        self.assertEqual(Decimal("15.00"), quote.markup_percent)
        self.assertEqual(2 * AUF_SCALE, quote.quoted_units)

    async def test_banana_pro_has_premium_sku_floor(self) -> None:
        quote = await quote_auf_payload(
            _Connection(
                model_alias="nano_banana_pro",
                resolution="4K",
                unit_cost_usd=Decimal("0.03"),
                override=None,
                quality_surcharge=2,
                minimum_velvets=4,
            ),
            self._payload(model="nano_banana_pro", resolution="4K"),
        )
        self.assertEqual(4 * AUF_SCALE, quote.quoted_units)
        self.assertEqual(4, quote.minimum_velvets)

    async def test_individual_price_preserves_wan_quality_tier(self) -> None:
        quote = await quote_auf_payload(
            _Connection(
                model_alias="wan_27_image",
                resolution="2K",
                unit_cost_usd=Decimal("0.08"),
                override=Decimal("15"),
                quality_surcharge=0,
                minimum_velvets=3,
            ),
            self._payload(model="wan_27_image", resolution="2K"),
        )
        self.assertEqual(3 * AUF_SCALE, quote.quoted_units)


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

    def test_migrations_define_global_policy_and_economy_guards(self) -> None:
        quality_migration = Path(
            "migrations/z028_auf_individual_markup_and_quality.sql"
        ).read_text(encoding="utf-8")
        hardening_migration = Path(
            "migrations/z031_auf_pricing_economy_hardening.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("auf_user_markup_overrides", quality_migration)
        self.assertIn("WHEN '2K' THEN 1", quality_migration)
        self.assertIn("WHEN '4K' THEN 2", quality_migration)
        self.assertIn("quote_rub_per_vl = 4.00000000", hardening_migration)
        self.assertIn("operational_cost_buffer_percent = 5.0000", hardening_migration)
        self.assertIn("minimum_user_markup_percent = 15.0000", hardening_migration)
        self.assertIn("minimum_velvets", hardening_migration)
        self.assertIn("model_alias = 'nano_banana_pro'", hardening_migration)
        self.assertNotIn("DELETE FROM auf_user_markup_overrides", hardening_migration)

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
