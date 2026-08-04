from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from velvet_bot.domains.auf_wallet.service import AUF_PACKAGES


class AufMarginPackageContractTests(unittest.TestCase):
    def test_entry_package_starts_at_one_hundred_rubles(self) -> None:
        self.assertEqual((20, 100, 250, 500, 1_000, 2_500), AUF_PACKAGES)

        migration = Path(
            "migrations/z029_auf_margin30_packages.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("(20,    100.00", migration)
        self.assertIn("package_auf = 40", migration)

    def test_global_markup_is_default_and_individual_overrides_survive(self) -> None:
        migration = Path(
            "migrations/z029_auf_margin30_packages.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("retail_markup_percent = 42.8600", migration)
        self.assertNotIn("DELETE FROM auf_user_markup_overrides", migration)
        self.assertIn("Individual user overrides remain intact", migration)

    def test_cheapest_package_preserves_thirty_percent_margin_floor(self) -> None:
        prices = {
            20: Decimal("100"),
            100: Decimal("429"),
            250: Decimal("1019"),
            500: Decimal("1890"),
            1000: Decimal("3590"),
            2500: Decimal("8590"),
        }
        rub_per_vl = min(price / Decimal(amount) for amount, price in prices.items())
        provider_cost_rub = Decimal("0.03") * Decimal("79.7257")
        gross_margin = (rub_per_vl - provider_cost_rub) / rub_per_vl

        self.assertEqual(Decimal("3.436"), rub_per_vl)
        self.assertGreaterEqual(gross_margin, Decimal("0.30"))


if __name__ == "__main__":
    unittest.main()
