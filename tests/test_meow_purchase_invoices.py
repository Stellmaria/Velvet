from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from velvet_bot.database import Database
from velvet_bot.domains.meow_wallet import (
    MeowInvoiceError,
    MeowInvoiceStatus,
    MeowPurchaseRepository,
    MeowPurchaseService,
    MeowWalletRepository,
    auf_to_units,
)
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID


class _FakeRuntimeService:
    async def require_workspace_access(self, *, workspace_id, actor_user_id):
        if int(actor_user_id) not in {77, GLOBAL_WORKSPACE_CREATOR_ID}:
            raise PermissionError("Нет доступа к пространству.")


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLMeowPurchaseInvoiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        self.repository = MeowPurchaseRepository(self.database)
        self.service = MeowPurchaseService(
            self.repository,
            _FakeRuntimeService(),
        )
        self.wallets = MeowWalletRepository(self.database)
        await self._reset()

    async def asyncTearDown(self) -> None:
        await self._reset()
        await self.database.close()

    async def _reset(self) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                "DELETE FROM meow_wallet_entries WHERE workspace_id = $1::BIGINT",
                DEFAULT_WORKSPACE_ID,
            )
            await connection.execute(
                "DELETE FROM meow_purchase_invoices WHERE workspace_id = $1::BIGINT",
                DEFAULT_WORKSPACE_ID,
            )
            await connection.execute(
                """
                INSERT INTO meow_wallets (
                    workspace_id, available_units, reserved_units, status
                )
                VALUES ($1::BIGINT, 0, 0, 'active')
                ON CONFLICT (workspace_id) DO UPDATE
                SET available_units = 0,
                    reserved_units = 0,
                    status = 'active',
                    updated_at = NOW()
                """,
                DEFAULT_WORKSPACE_ID,
            )
            await connection.execute(
                """
                UPDATE meow_economy_settings
                SET provider_auf_usd = 0.02,
                    retail_auf_usd = 0.03,
                    billing_usd_to_rub = 79.85,
                    updated_at = NOW()
                WHERE singleton_id = 1
                """
            )

    async def _invoice(self, *, key: str, package: int = 100):
        return await self.service.create_invoice(
            workspace_id=DEFAULT_WORKSPACE_ID,
            package_auf=package,
            actor_user_id=77,
            idempotency_key=f"test:purchase:{key}",
        )

    async def test_invoice_locks_package_price_and_exchange_rate(self) -> None:
        invoice = await self._invoice(key="locked", package=100)
        self.assertEqual(Decimal("3.00"), invoice.package_price_usd)
        self.assertEqual(Decimal("79.85000000"), invoice.locked_exchange_rate)
        self.assertEqual(Decimal("240.00"), invoice.final_local_amount)

        async with self.database.acquire() as connection:
            await connection.execute(
                """
                UPDATE meow_economy_settings
                SET billing_usd_to_rub = 100, updated_at = NOW()
                WHERE singleton_id = 1
                """
            )
        stored = await self.repository.invoice_by_code(invoice.public_code)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(Decimal("240.00"), stored.final_local_amount)
        self.assertEqual(Decimal("79.85000000"), stored.locked_exchange_rate)

    async def test_invoice_creation_is_idempotent(self) -> None:
        first = await self._invoice(key="dedupe", package=40)
        second = await self._invoice(key="dedupe", package=40)
        self.assertEqual(first.id, second.id)
        async with self.database.acquire() as connection:
            count = await connection.fetchval(
                """
                SELECT COUNT(*) FROM meow_purchase_invoices
                WHERE idempotency_key = 'test:purchase:dedupe'
                """
            )
        self.assertEqual(1, int(count or 0))

    async def test_confirm_paid_credits_wallet_exactly_once(self) -> None:
        invoice = await self._invoice(key="paid", package=250)
        for _ in range(2):
            paid, wallet = await self.service.confirm_paid(
                public_code=invoice.public_code,
                actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            )
            self.assertIs(MeowInvoiceStatus.PAID, paid.status)
            self.assertEqual(auf_to_units(250), wallet.available_units)

        overview = await self.wallets.overview(DEFAULT_WORKSPACE_ID)
        self.assertEqual(auf_to_units(250), overview.wallet.available_units)
        purchases = [
            entry
            for entry in overview.recent_entries
            if entry.invoice_id == invoice.id
        ]
        self.assertEqual(1, len(purchases))

    async def test_only_stell_can_confirm_payment(self) -> None:
        invoice = await self._invoice(key="access")
        with self.assertRaises(PermissionError):
            await self.service.confirm_paid(
                public_code=invoice.public_code,
                actor_user_id=77,
            )

    async def test_cancelled_invoice_cannot_be_paid(self) -> None:
        invoice = await self._invoice(key="cancel")
        cancelled = await self.service.cancel_invoice(
            public_code=invoice.public_code,
            workspace_id=DEFAULT_WORKSPACE_ID,
            actor_user_id=77,
        )
        self.assertIs(MeowInvoiceStatus.CANCELLED, cancelled.status)
        with self.assertRaises(MeowInvoiceError):
            await self.service.confirm_paid(
                public_code=invoice.public_code,
                actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            )

    async def test_expiry_job_marks_old_created_invoice(self) -> None:
        invoice = await self._invoice(key="expire")
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                UPDATE meow_purchase_invoices
                SET expires_at = $2::TIMESTAMPTZ
                WHERE id = $1::UUID
                """,
                invoice.id,
                datetime.now(timezone.utc) - timedelta(minutes=1),
            )
        self.assertEqual(1, await self.repository.expire_invoices())
        stored = await self.repository.invoice_by_code(invoice.public_code)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertIs(MeowInvoiceStatus.EXPIRED, stored.status)

    async def test_reconciliation_detects_wallet_ledger_mismatch(self) -> None:
        invoice = await self._invoice(key="reconcile", package=40)
        await self.service.confirm_paid(
            public_code=invoice.public_code,
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
        )
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                UPDATE meow_wallets
                SET available_units = available_units + 1
                WHERE workspace_id = $1::BIGINT
                """,
                DEFAULT_WORKSPACE_ID,
            )
        issues = await self.repository.reconciliation_issues()
        self.assertIn("wallet_ledger_mismatch", {item.code for item in issues})


if __name__ == "__main__":
    unittest.main()
