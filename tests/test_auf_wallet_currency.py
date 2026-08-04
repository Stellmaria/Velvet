from __future__ import annotations

import inspect
import unittest
from decimal import Decimal

from velvet_bot.app import auf_wallet_currency_ui as currency_ui
from velvet_bot.app import auf_wallet_ui_install
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback


class AufWalletCurrencyTests(unittest.TestCase):
    def test_currency_normalization_and_callback_compatibility(self) -> None:
        self.assertEqual("USD", currency_ui._normalize_currency("usd"))
        self.assertEqual("RUB", currency_ui._normalize_currency("eur"))
        self.assertEqual("20|USD", currency_ui._package_callback_value(20, "usd"))
        self.assertEqual((20, "USD"), currency_ui._parse_package_callback_value("20|USD"))
        self.assertEqual((40, "RUB"), currency_ui._parse_package_callback_value("40"))

    def test_package_values_pack_and_round_trip_without_aiogram_separator(self) -> None:
        for amount in currency_ui.legacy.AUF_PACKAGES:
            for currency in ("RUB", "USD"):
                with self.subTest(amount=amount, currency=currency):
                    value = currency_ui._package_callback_value(amount, currency)
                    self.assertNotIn(":", value)
                    packed = AufCallback(
                        action="wallet_buy",
                        workspace_id=17,
                        value=value,
                    ).pack()
                    self.assertLessEqual(len(packed.encode("utf-8")), 64)
                    unpacked = AufCallback.unpack(packed)
                    self.assertEqual("wallet_buy", unpacked.action)
                    self.assertEqual(
                        (amount, currency),
                        currency_ui._parse_package_callback_value(unpacked.value),
                    )

    def test_wallet_keyboards_pack_for_rub_and_usd(self) -> None:
        for currency in ("RUB", "USD"):
            with self.subTest(currency=currency):
                keyboard = currency_ui._wallet_keyboard(
                    workspace_id=17,
                    global_owner=True,
                    frozen=False,
                    invoices=(),
                    currency=currency,
                )
                decoded_packages: list[tuple[int, str]] = []
                for row in keyboard.inline_keyboard:
                    for button in row:
                        callback_data = button.callback_data
                        if callback_data is None:
                            continue
                        self.assertLessEqual(len(callback_data.encode("utf-8")), 64)
                        if not callback_data.startswith("auf:"):
                            continue
                        callback = AufCallback.unpack(callback_data)
                        if callback.action != "wallet_buy":
                            continue
                        self.assertNotIn(":", callback.value)
                        decoded_packages.append(
                            currency_ui._parse_package_callback_value(callback.value)
                        )
                self.assertEqual(
                    [(amount, currency) for amount in currency_ui.legacy.AUF_PACKAGES],
                    decoded_packages,
                )

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
