from __future__ import annotations

import inspect
import unittest
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from velvet_bot.app import auf_margin_dashboard_install, composition
from velvet_bot.domains.auf_wallet.charged_queue import _reserve_charge
from velvet_bot.domains.auf_wallet.economics import (
    AufEconomicsRepository,
    format_margin_summary,
)
from velvet_bot.domains.auf_wallet.models import AUF_SCALE, AufMarginSummary


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Connection:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self) -> _Transaction:
        return _Transaction()

    async def fetchrow(self, query: str, *args):
        if "FROM auf_generation_pnl" in query and "COUNT(*)" in query:
            return {
                "generations": 4,
                "captured_units": 7 * AUF_SCALE,
                "revenue": Decimal("0.35000000"),
                "provider_cost": Decimal("0.14000000"),
                "reserve": Decimal("0.00700000"),
                "profit": Decimal("0.20300000"),
                "margin_percent": Decimal("58.0000"),
                "subsidy": Decimal("0"),
                "subsidized": 0,
                "estimated_basis": 1,
            }
        if "JOIN auf_generation_pnl" in query:
            return {
                "status": "captured",
                "realized_revenue_usd": Decimal("0.10"),
                "operational_reserve_usd": Decimal("0.005"),
            }
        raise AssertionError(query)

    async def execute(self, query: str, *args):
        self.executions.append((query, args))
        return "UPDATE 1"


class _Acquire:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Database:
    def __init__(self) -> None:
        self.connection = _Connection()

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)


class AufMarginAccountingTests(unittest.IsolatedAsyncioTestCase):
    async def test_margin_summary_aggregates_realized_generation_economics(self) -> None:
        summary = await AufEconomicsRepository(_Database()).margin_summary(days=30)
        self.assertEqual(4, summary.generations)
        self.assertEqual(7 * AUF_SCALE, summary.captured_units)
        self.assertEqual(Decimal("0.20300000"), summary.contribution_profit_usd)
        self.assertEqual(Decimal("58.0000"), summary.contribution_margin_percent)
        self.assertEqual(1, summary.estimated_basis_generations)

    async def test_actual_provider_cost_recalculates_pnl(self) -> None:
        database = _Database()
        task_id = uuid4()
        await AufEconomicsRepository(database).record_actual_provider_cost(
            task_id=task_id,
            actual_provider_cost_usd=Decimal("0.06"),
        )
        self.assertEqual(2, len(database.connection.executions))
        charge_update, pnl_update = database.connection.executions
        self.assertIn("UPDATE auf_task_charges", charge_update[0])
        self.assertIn("UPDATE auf_generation_pnl", pnl_update[0])
        self.assertEqual(Decimal("0.035"), pnl_update[1][2])
        self.assertEqual(Decimal("35.00"), pnl_update[1][3])
        self.assertEqual(Decimal("0"), pnl_update[1][4])

    def test_owner_margin_summary_marks_estimated_basis(self) -> None:
        text = format_margin_summary(
            AufMarginSummary(
                days=30,
                generations=2,
                captured_units=3 * AUF_SCALE,
                realized_revenue_usd=Decimal("0.12"),
                provider_cost_usd=Decimal("0.05"),
                operational_reserve_usd=Decimal("0.0025"),
                contribution_profit_usd=Decimal("0.0675"),
                contribution_margin_percent=Decimal("56.25"),
                subsidy_usd=Decimal("0"),
                subsidized_generations=0,
                estimated_basis_generations=1,
            )
        )
        self.assertIn("P&amp;L генераций", text)
        self.assertIn("Маржа: <b>56.25%</b>", text)
        self.assertIn("Оценочная база: <b>1</b>", text)


class AufMarginAccountingContractTests(unittest.TestCase):
    def test_migrations_define_fifo_lots_pnl_and_non_task_debits(self) -> None:
        accounting = Path("migrations/z033_auf_margin_accounting.sql").read_text(
            encoding="utf-8"
        )
        debits = Path("migrations/z034_auf_revenue_lot_debits.sql").read_text(
            encoding="utf-8"
        )
        settlement_fix = Path(
            "migrations/z035_auf_settlement_basis_quality_fix.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS auf_revenue_lots", accounting)
        self.assertIn("allocate_auf_charge_revenue", accounting)
        self.assertIn("CREATE TABLE IF NOT EXISTS auf_generation_pnl", accounting)
        self.assertIn("CREATE OR REPLACE VIEW auf_generation_margin_daily", accounting)
        self.assertIn("allow_subsidized_generations = FALSE", accounting)
        self.assertIn("auf_wallet_debit_lot_allocations", debits)
        self.assertIn("consume_auf_wallet_debit_revenue", debits)
        self.assertIn("'manual_debit', 'adjustment'", debits)
        self.assertIn("allocation.basis_quality", settlement_fix)
        self.assertIn("resolved_basis_quality", settlement_fix)
        self.assertNotIn("COUNT(DISTINCT basis_quality)", settlement_fix)

    def test_charge_snapshot_contains_auditable_pricing_fields(self) -> None:
        source = inspect.getsource(_reserve_charge)
        for field in (
            "pricing_strategy",
            "target_margin_percent",
            "operational_reserve_usd",
            "minimum_revenue_usd",
            "subsidy_guard_applied",
        ):
            self.assertIn(field, source)

    def test_owner_dashboard_is_installed_after_pricing_ui(self) -> None:
        stages = composition._FEATURE_STAGE_NAMES
        self.assertLess(
            stages.index("install_auf_owner_pricing_ui"),
            stages.index("install_auf_margin_dashboard"),
        )
        source = inspect.getsource(
            auf_margin_dashboard_install.install_auf_margin_dashboard
        )
        self.assertIn("wallet_pnl", source)
        self.assertIn("margin_summary", source)
        self.assertIn("global_owner", source)


if __name__ == "__main__":
    unittest.main()
