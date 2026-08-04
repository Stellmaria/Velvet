from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP

from velvet_bot.app import auf_wallet_currency_ui
from velvet_bot.domains.auf_wallet import AufPurchaseService


async def set_invoice_currency_from_fixed_package_price(
    purchase_service: AufPurchaseService,
    invoice,
    currency: str,
):
    selected_currency = auf_wallet_currency_ui._normalize_currency(currency)
    if selected_currency == "RUB":
        return invoice

    repository = getattr(purchase_service, "_repository", None)
    database = getattr(repository, "_database", None)
    if database is None:
        raise RuntimeError("Хранилище счетов недоступно для выбора валюты.")

    usd_amount = (
        Decimal(invoice.final_local_amount) / Decimal(invoice.locked_exchange_rate)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    async with database.acquire() as connection:
        row = await connection.fetchrow(
            """
            UPDATE auf_purchase_invoices
            SET billing_currency = 'USD',
                package_price_usd = $2::NUMERIC,
                final_local_amount = $2::NUMERIC,
                updated_at = NOW()
            WHERE id = $1::UUID
              AND status = 'created'
            RETURNING package_price_usd
            """,
            invoice.id,
            usd_amount,
        )
    if row is None:
        raise RuntimeError("Не удалось зафиксировать валюту счёта.")

    return replace(
        invoice,
        package_price_usd=usd_amount,
        billing_currency="USD",
        final_local_amount=usd_amount,
    )


def install_auf_wallet_currency_fix() -> None:
    auf_wallet_currency_ui._set_invoice_currency = (
        set_invoice_currency_from_fixed_package_price
    )


__all__ = (
    "install_auf_wallet_currency_fix",
    "set_invoice_currency_from_fixed_package_price",
)
