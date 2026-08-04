from __future__ import annotations

import inspect
import unittest
from decimal import Decimal

from velvet_bot.app import auf_wallet_currency_ui as currency_ui
from velvet_bot.app import auf_wallet_ui_install


class AufWalletCurrencyTests(unittest.TestCase):
    def test_currency_normalization_and_callback_compatibility(self) -> None:
        self.assertEqual("USD", currency_ui._normalize_currency("usd"))
        self.assertEqual("RUB", currency_ui._normalize_currency("eur"))
        self.assertEqual("20:USD", currency_ui._package_callback_value(20, "usd"))
        self.assertEqual((20, "USD"), currency_ui._parse_package_callback_value("20:USD"))
        self.assertEqual((40, "RUB"), currency_ui._parse_package_callback_value("40"))

    def test_money_format_uses_selected_currency(self) -> None:
        self.assertEqual("100 ₽", currency_ui._format_money(Decimal("100"), "RUB"))
        self.assertEqual("$5.37", currency_ui._format_money(Decimal("5.37"), "USD"))

    def test_wallet_displays_both_prices_and_routes_currency_to_service(self) -> None:
        render_source = inspect.getsource(currency_ui._render_wallet)
        handler_source = inspect.getsource(currency_ui.handle_auf_wallet_action)
        self.assertIn("quote.price_rub", render_source)
        self.assertIn("quote.price_usd", render_source)
        self.assertIn("Валюта нового счёта", render_source)
        self.assertIn("billing_currency=selected_currency", handler_source)
        self.assertNotIn("database.acquire", inspect.getsource(currency_ui))

    def test_installer_routes_directly_to_currency_ui(self) -> None:
        source = inspect.getsource(auf_wallet_ui_install)
        self.assertIn("auf_wallet_currency_ui", source)
        self.assertNotIn("auf_wallet_currency_fix", source)


if __name__ == "__main__":
    unittest.main()
