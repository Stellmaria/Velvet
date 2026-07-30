from __future__ import annotations

from decimal import Decimal

from velvet_bot.database import Database


async def active_package_prices(database: Database) -> dict[int, Decimal]:
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT package_auf, price_rub
            FROM auf_package_prices
            WHERE is_active = TRUE
              AND effective_from <= NOW()
              AND (effective_to IS NULL OR effective_to > NOW())
            ORDER BY package_auf
            """
        )
    return {int(row["package_auf"]): Decimal(row["price_rub"]) for row in rows}


async def active_package_price(database: Database, package_auf: int) -> Decimal | None:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT price_rub
            FROM auf_package_prices
            WHERE package_auf = $1::INTEGER
              AND is_active = TRUE
              AND effective_from <= NOW()
              AND (effective_to IS NULL OR effective_to > NOW())
            """,
            int(package_auf),
        )
    return Decimal(value) if value is not None else None


__all__ = ("active_package_price", "active_package_prices")
