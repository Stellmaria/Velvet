from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from velvet_bot.domains.auf_wallet.service import AUF_PACKAGES


PRICES = {
    20: Decimal("100"),
    50: Decimal("239"),
    75: Decimal("339"),
    100: Decimal("429"),
    150: Decimal("619"),
    250: Decimal("999"),
}


class AufMarginPackageContractTests(unittest.TestCase):
    def test_package_ladder_starts_at_one_hundred_rubles_and_stops_at_250(self) -> None:
        self.assertEqual((20, 50, 75, 100, 150, 250), AUF_PACKAGES)

        migration = Path(
            "migrations/z030_auf_package_ladder_to_250.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("NOT IN (20, 50, 75, 100, 150, 250)", migration)
        self.assertIn("(20,  100.00", migration)
        self.assertIn("(250, 999.00", migration)

    def test_global_markup_is_default_and_individual_overrides_survive(self) -> None:
        markup_migration = Path(
            "migrations/z029_auf_margin30_packages.sql"
        ).read_text(encoding="utf-8")
        ladder_migration = Path(
            "migrations/z030_auf_package_ladder_to_250.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("retail_markup_percent = 42.8600", markup_migration)
        self.assertNotIn("DELETE FROM auf_user_markup_overrides", markup_migration)
        self.assertNotIn("DELETE FROM auf_user_markup_overrides", ladder_migration)

    def test_price_per_vl_decreases_smoothly_and_preserves_margin(self) -> None:
        unit_prices = [PRICES[amount] / Decimal(amount) for amount in AUF_PACKAGES]
        self.assertEqual(sorted(unit_prices, reverse=True), unit_prices)
        self.assertEqual(Decimal("5"), unit_prices[0])
        self.assertEqual(Decimal("3.996"), unit_prices[-1])

        provider_cost_rub = Decimal("0.03") * Decimal("79.7257")
        gross_margin = (unit_prices[-1] - provider_cost_rub) / unit_prices[-1]
        self.assertGreaterEqual(gross_margin, Decimal("0.30"))

    def test_comparable_packages_remain_competitive_without_deep_dumping(self) -> None:
        competitor_prices = {
            20: Decimal("129"),
            50: Decimal("299"),
            100: Decimal("589"),
        }
        for amount, competitor_price in competitor_prices.items():
            discount = (competitor_price - PRICES[amount]) / competitor_price
            with self.subTest(amount=amount):
                self.assertGreaterEqual(discount, Decimal("0.15"))
                self.assertLessEqual(discount, Decimal("0.35"))

        competitor_best_unit_price = Decimal("1729") / Decimal("300")
        self.assertLess(PRICES[250] / Decimal("250"), competitor_best_unit_price)


if __name__ == "__main__":
    unittest.main()
