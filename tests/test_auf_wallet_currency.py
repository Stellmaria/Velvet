from __future__ import annotations

import inspect
import unittest
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from velvet_bot.app import auf_wallet_currency_fix
from velvet_bot.app import auf_wallet_currency_ui as currency_ui
from velvet_bot.app import auf_wallet_ui_install


@dataclass(frozen=True, slots=True)
class _Invoice:
    id: UUID
    package_price_usd: Decimal
    billing_currency: str
    locked_exchange_rate: Decimal
    final_local_amount: Decimal


class _Connection:
    def __init__(self) -> None:
        self.query = ""
        self.invoice_id = None
        self.usd_amount = None

    async def fetchrow(self, query: str, invoice_id: UUID, usd_amount: Decimal):
        self.query = query
        self.invoice_id = invoice_id
        self.usd_amount = usd_amount
        return {"package_price_usd": usd_amount}


class _Acquire:
    def __init__(self, connection: _Connection) -> None:
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


class AufWalletCurrencyTests(unittest.IsolatedAsyncioTestCase):
    def test_currency_normalization_and_callback_compatibility(self) -> None:
        self.assertEqual("USD", currency_ui._normalize_currency("usd"))
        self.assertEqual("RUB", currency_ui._normalize_currency("eur"))
        self.assertEqual("20:USD", currency_ui._package_callback_value(20, "usd"))
        self.assertEqual((20, "USD"), currency_ui._parse_package_callback_value("20:USD"))
        self.assertEqual((40, "RUB"), currency_ui._parse_package_callback_value("40"))

    def test_money_format_uses_selected_currency(self) -> None:
        self.assertEqual("100 ₽", currency_ui._format_money(Decimal("100"), "RUB"))
        self.assertEqual("$5.37", currency_ui._format_money(Decimal("5.37"), "USD"))

    async def test_usd_invoice_uses_fixed_rub_package_price(self) -> None:
        database = _Database()
        service = SimpleNamespace(
            _repository=SimpleNamespace(_database=database),
        )
        invoice = _Invoice(
            id=UUID("00000000-0000-0000-0000-000000000123"),
            package_price_usd=Decimal("3.00"),
            billing_currency="RUB",
            locked_exchange_rate=Decimal("79.85"),
            final_local_amount=Decimal("429.00"),
        )

        updated = await (
            auf_wallet_currency_fix.set_invoice_currency_from_fixed_package_price(
                service,
                invoice,
                "USD",
            )
        )

        self.assertEqual("USD", updated.billing_currency)
        self.assertEqual(Decimal("5.37"), updated.package_price_usd)
        self.assertEqual(Decimal("5.37"), updated.final_local_amount)
        self.assertEqual(invoice.id, database.connection.invoice_id)
        self.assertEqual(Decimal("5.37"), database.connection.usd_amount)
        self.assertIn("billing_currency = 'USD'", database.connection.query)
        self.assertIn("package_price_usd = $2::NUMERIC", database.connection.query)
        self.assertIn("final_local_amount = $2::NUMERIC", database.connection.query)

    def test_wallet_displays_both_prices_and_routes_currency_ui(self) -> None:
        render_source = inspect.getsource(currency_ui._render_wallet)
        self.assertIn("quote.price_rub", render_source)
        self.assertIn("quote.price_usd", render_source)
        self.assertIn("Валюта нового счёта", render_source)

        install_source = inspect.getsource(auf_wallet_ui_install)
        self.assertIn("auf_wallet_currency_ui", install_source)
        self.assertIn("install_auf_wallet_currency_fix", install_source)


if __name__ == "__main__":
    unittest.main()
