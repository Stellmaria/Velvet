from __future__ import annotations

import inspect
import unittest
from decimal import Decimal
from types import SimpleNamespace

from velvet_bot.app import (
    auf_charged_queue_install,
    auf_generation_price_privacy_install as price_privacy,
)
from velvet_bot.domains.auf_wallet.models import AUF_SCALE
from velvet_bot.domains.auf_wallet.pricing import (
    AufPriceQuote,
    format_owner_price_details,
    quote_auf_payload,
)
from velvet_bot.domains.media_generation import KieModelAlias


class _Connection:
    def __init__(
        self,
        *,
        model_alias: str,
        resolution: str,
        unit_cost_usd: Decimal,
        override: Decimal | None = None,
    ) -> None:
        self.model_alias = model_alias
        self.resolution = resolution
        self.unit_cost_usd = unit_cost_usd
        self.override = override

    async def fetchrow(self, query: str, *args):
        if "FROM auf_price_versions" in query:
            minimums = {
                "nano_banana_2": {"1K": 1, "2K": 2, "4K": 3},
                "nano_banana_pro": {"1K": 2, "2K": 3, "4K": 4},
                "wan_27_image": {"1K": 1, "2K": 2},
                "wan_27_image_pro": {"1K": 3, "2K": 4, "4K": 5},
            }
            return {
                "id": 1,
                "version_key": "pricing:test",
                "provider": "grs",
                "model_alias": self.model_alias,
                "resolution": self.resolution,
                "audio": None,
                "pricing_basis": "fixed",
                "unit_cost_usd": self.unit_cost_usd,
                "extra_reference_cost_usd": Decimal("0"),
                "quality_surcharge_velvets": 0,
                "minimum_velvets": minimums[self.model_alias][self.resolution],
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


def _payload(model: str, resolution: str) -> dict[str, object]:
    return {
        "user_id": 55,
        "request": {
            "model": model,
            "resolution": resolution,
            "duration_seconds": 6,
            "references": [],
            "extra_input": {},
        },
    }


class BananaPriceTests(unittest.IsolatedAsyncioTestCase):
    async def test_banana_and_banana_pro_keep_distinct_quality_grids(self) -> None:
        expected_by_model = {
            "nano_banana_2": {"1K": 1, "2K": 2, "4K": 3},
            "nano_banana_pro": {"1K": 2, "2K": 3, "4K": 4},
        }
        costs = {
            "nano_banana_2": Decimal("0.02"),
            "nano_banana_pro": Decimal("0.03"),
        }
        for model, expected in expected_by_model.items():
            for resolution, velvets in expected.items():
                with self.subTest(model=model, resolution=resolution):
                    quote = await quote_auf_payload(
                        _Connection(
                            model_alias=model,
                            resolution=resolution,
                            unit_cost_usd=costs[model],
                        ),
                        _payload(model, resolution),
                    )
                    self.assertEqual(velvets * AUF_SCALE, quote.quoted_units)

    async def test_individual_markup_preserves_banana_pro_floor(self) -> None:
        quote = await quote_auf_payload(
            _Connection(
                model_alias="nano_banana_pro",
                resolution="1K",
                unit_cost_usd=Decimal("0.03"),
                override=Decimal("15"),
            ),
            _payload("nano_banana_pro", "1K"),
        )
        self.assertEqual(2 * AUF_SCALE, quote.quoted_units)


class WanImagePriceTests(unittest.IsolatedAsyncioTestCase):
    async def test_standard_and_pro_keep_separate_price_grids(self) -> None:
        expected_by_model = {
            "wan_27_image": {"1K": 1, "2K": 2},
            "wan_27_image_pro": {"1K": 3, "2K": 4, "4K": 5},
        }
        costs = {
            "wan_27_image": Decimal("0.03"),
            "wan_27_image_pro": Decimal("0.075"),
        }
        for model, expected in expected_by_model.items():
            for resolution, velvets in expected.items():
                with self.subTest(model=model, resolution=resolution):
                    quote = await quote_auf_payload(
                        _Connection(
                            model_alias=model,
                            resolution=resolution,
                            unit_cost_usd=costs[model],
                        ),
                        _payload(model, resolution),
                    )
                    self.assertEqual(velvets * AUF_SCALE, quote.quoted_units)

    async def test_individual_markup_does_not_collapse_wan_pro_floor(self) -> None:
        quote = await quote_auf_payload(
            _Connection(
                model_alias="wan_27_image_pro",
                resolution="1K",
                unit_cost_usd=Decimal("0.075"),
                override=Decimal("15"),
            ),
            _payload("wan_27_image_pro", "1K"),
        )
        self.assertEqual(3 * AUF_SCALE, quote.quoted_units)


class OwnerCostOnlyTests(unittest.TestCase):
    @staticmethod
    def _quote() -> AufPriceQuote:
        return AufPriceQuote(
            price_version_id=1,
            version_key="pricing:test",
            provider="kie",
            model_alias="seedream_5_pro",
            resolution="2K",
            audio=None,
            duration_seconds=6,
            reference_count=1,
            provider_cost_usd=Decimal("0.15"),
            global_markup_percent=Decimal("42.86"),
            user_markup_override_percent=None,
            minimum_user_markup_percent=Decimal("15"),
            markup_percent=Decimal("42.86"),
            operational_cost_buffer_percent=Decimal("5"),
            quote_rub_per_vl=Decimal("4"),
            quality_surcharge_velvets=0,
            minimum_velvets=4,
            target_retail_usd=Decimal("0.2250045"),
            minimum_revenue_usd=Decimal("0.250860"),
            billing_usd_to_rub=Decimal("79.7257"),
            billing_usd_to_byn=Decimal("2.92661"),
            quoted_units=5 * AUF_SCALE,
        )

    def test_owner_block_contains_only_provider_and_real_cost(self) -> None:
        rendered = format_owner_price_details(self._quote())

        self.assertIn("Провайдер: <code>KIE</code>", rendered)
        self.assertIn("$0.1500", rendered)
        self.assertIn("₽ РФ", rendered)
        self.assertIn("Br", rendered)
        for forbidden in (
            "Наценка",
            "Цена по проценту",
            "Надбавка качества",
            "Списание",
            "Выручка",
            "Прибыль",
            "маржа",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_owner_generation_screens_do_not_restore_wallet_economics(self) -> None:
        for renderer in (
            price_privacy._show_photo_review,
            price_privacy._show_video_review,
        ):
            source = inspect.getsource(renderer)
            self.assertNotIn("Учётная цена", source)
            self.assertNotIn("Списание Стэл", source)
            self.assertNotIn("Надбавка за выбранное качество", source)

    def test_seedream_notice_discloses_only_reference_dependency(self) -> None:
        request = SimpleNamespace(
            model=KieModelAlias.SEEDREAM_5_PRO,
            references=(object(), object(), object()),
        )
        rendered = "\n".join(price_privacy._seedream_reference_notice(request))
        self.assertIn("зависит от количества референсов", rendered)
        self.assertIn("учтено: <b>3</b>", rendered)
        self.assertNotIn("$", rendered)
        self.assertNotIn("₽", rendered)
        self.assertNotIn("Br", rendered)

    def test_wan_result_label_supports_multiple_images(self) -> None:
        self.assertEqual("1 изображение", price_privacy._result_label(1))
        self.assertEqual("2 изображения", price_privacy._result_label(2))
        self.assertEqual("12 изображений", price_privacy._result_label(12))

    def test_charged_queue_rebinds_runtime_quote(self) -> None:
        source = inspect.getsource(auf_charged_queue_install)
        self.assertIn(
            "charged_queue.quote_auf_payload = pricing.quote_auf_payload",
            source,
        )
        self.assertIn("install_auf_generation_price_privacy", source)


if __name__ == "__main__":
    unittest.main()
