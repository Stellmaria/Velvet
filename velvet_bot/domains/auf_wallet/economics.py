from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from velvet_bot.database import Database

from .models import AufMarginSummary


class AufEconomicsRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def margin_summary(self, *, days: int = 30) -> AufMarginSummary:
        safe_days = max(1, min(int(days), 366))
        cutoff = datetime.now(timezone.utc) - timedelta(days=safe_days)
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT COUNT(*) AS generations,
                       COALESCE(SUM(captured_units), 0) AS captured_units,
                       COALESCE(SUM(realized_revenue_usd), 0) AS revenue,
                       COALESCE(SUM(provider_cost_usd), 0) AS provider_cost,
                       COALESCE(SUM(operational_reserve_usd), 0) AS reserve,
                       COALESCE(SUM(contribution_profit_usd), 0) AS profit,
                       CASE
                           WHEN COALESCE(SUM(realized_revenue_usd), 0) > 0
                               THEN SUM(contribution_profit_usd)
                                    / SUM(realized_revenue_usd) * 100
                           ELSE NULL
                       END AS margin_percent,
                       COALESCE(SUM(subsidy_usd), 0) AS subsidy,
                       COUNT(*) FILTER (WHERE subsidy_usd > 0) AS subsidized,
                       COUNT(*) FILTER (
                           WHERE revenue_basis_quality <> 'actual'
                       ) AS estimated_basis
                FROM auf_generation_pnl
                WHERE captured_at >= $1::TIMESTAMPTZ
                """,
                cutoff,
            )
        if row is None:
            raise RuntimeError("Не удалось построить отчёт экономики Ауф.")
        margin = row["margin_percent"]
        return AufMarginSummary(
            days=safe_days,
            generations=int(row["generations"] or 0),
            captured_units=int(row["captured_units"] or 0),
            realized_revenue_usd=Decimal(row["revenue"] or 0),
            provider_cost_usd=Decimal(row["provider_cost"] or 0),
            operational_reserve_usd=Decimal(row["reserve"] or 0),
            contribution_profit_usd=Decimal(row["profit"] or 0),
            contribution_margin_percent=(
                Decimal(margin) if margin is not None else None
            ),
            subsidy_usd=Decimal(row["subsidy"] or 0),
            subsidized_generations=int(row["subsidized"] or 0),
            estimated_basis_generations=int(row["estimated_basis"] or 0),
        )

    async def record_actual_provider_cost(
        self,
        *,
        task_id: UUID,
        actual_provider_cost_usd: Decimal,
    ) -> None:
        cost = Decimal(actual_provider_cost_usd).quantize(Decimal("0.00000001"))
        if not cost.is_finite() or cost <= 0:
            raise ValueError("Фактическая себестоимость должна быть больше нуля.")

        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT charge.status, pnl.realized_revenue_usd,
                           pnl.operational_reserve_usd
                    FROM auf_task_charges AS charge
                    JOIN auf_generation_pnl AS pnl ON pnl.task_id = charge.task_id
                    WHERE charge.task_id = $1::UUID
                    FOR UPDATE OF charge, pnl
                    """,
                    task_id,
                )
                if row is None or str(row["status"]) != "captured":
                    raise ValueError(
                        "Фактическую себестоимость можно записать только "
                        "для успешно списанной генерации."
                    )
                revenue = Decimal(row["realized_revenue_usd"])
                reserve = Decimal(row["operational_reserve_usd"])
                profit = revenue - cost - reserve
                margin = (
                    profit / revenue * Decimal("100")
                    if revenue > 0
                    else None
                )
                subsidy = max(cost + reserve - revenue, Decimal("0"))

                await connection.execute(
                    """
                    UPDATE auf_task_charges
                    SET actual_provider_cost_usd = $2::NUMERIC,
                        updated_at = NOW()
                    WHERE task_id = $1::UUID
                    """,
                    task_id,
                    cost,
                )
                await connection.execute(
                    """
                    UPDATE auf_generation_pnl
                    SET provider_cost_usd = $2::NUMERIC,
                        contribution_profit_usd = $3::NUMERIC,
                        contribution_margin_percent = $4::NUMERIC,
                        subsidy_usd = $5::NUMERIC
                    WHERE task_id = $1::UUID
                    """,
                    task_id,
                    cost,
                    profit,
                    margin,
                    subsidy,
                )


def format_margin_summary(summary: AufMarginSummary) -> str:
    if summary.generations == 0:
        return (
            f"<b>P&amp;L генераций · {summary.days} дней</b>\n"
            "Успешных платных генераций пока нет."
        )
    margin = (
        f"{summary.contribution_margin_percent:.2f}%"
        if summary.contribution_margin_percent is not None
        else "нет выручки"
    )
    basis_note = (
        f"\nОценочная база: <b>{summary.estimated_basis_generations}</b> генераций."
        if summary.estimated_basis_generations
        else ""
    )
    return (
        f"<b>P&amp;L генераций · {summary.days} дней</b>\n"
        f"Генерации: <b>{summary.generations}</b>\n"
        f"Выручка по FIFO-лотам: <b>${summary.realized_revenue_usd:.4f}</b>\n"
        f"Провайдеры: <b>${summary.provider_cost_usd:.4f}</b>\n"
        f"Операционный резерв: <b>${summary.operational_reserve_usd:.4f}</b>\n"
        f"Вклад в прибыль: <b>${summary.contribution_profit_usd:.4f}</b>\n"
        f"Маржа: <b>{margin}</b>\n"
        f"Субсидия: <b>${summary.subsidy_usd:.4f}</b> · "
        f"{summary.subsidized_generations} генераций"
        f"{basis_note}"
    )


__all__ = (
    "AufEconomicsRepository",
    "format_margin_summary",
)
