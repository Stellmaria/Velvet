from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from velvet_bot.database import Database
from velvet_bot.domains.auf_wallet import (
    AUF_SCALE,
    AufEconomySettings,
    AufInsufficientBalance,
    AufWalletAccessError,
    AufWalletRepository,
    AufWalletService,
    AufWalletStatus,
    auf_to_units,
    format_auf_units,
    units_to_auf,
)
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID


class _FakeRuntimeService:
    async def require_workspace_access(self, *, workspace_id, actor_user_id):
        if actor_user_id not in {77, GLOBAL_WORKSPACE_CREATOR_ID}:
            raise PermissionError("Нет доступа.")


class _FakeRepository:
    def __init__(self) -> None:
        self.settings = AufEconomySettings(
            provider_auf_usd=Decimal("0.02"),
            retail_auf_usd=Decimal("0.03"),
            billing_usd_to_rub=Decimal("79.85"),
            updated_by_user_id=None,
            updated_at=datetime.now(timezone.utc),
        )

    async def economy_settings(self):
        return self.settings


class AufWalletValueTests(unittest.TestCase):
    def test_auf_uses_exact_integer_units(self) -> None:
        self.assertEqual(AUF_SCALE, auf_to_units("1"))
        self.assertEqual(21_875, auf_to_units("2.1875"))
        self.assertEqual(Decimal("2.1875"), units_to_auf(21_875))
        self.assertEqual("2.19 Ауф", format_auf_units(21_875))


class AufWalletServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_package_prices_follow_usd_rate(self) -> None:
        service = AufWalletService(_FakeRepository(), _FakeRuntimeService())
        quotes = await service.package_quotes(workspace_id=7, actor_user_id=77)
        self.assertEqual((40, 100, 250, 500, 1000, 2500), tuple(q.amount_auf for q in quotes))
        self.assertEqual(Decimal("1.20"), quotes[0].price_usd)
        self.assertEqual(Decimal("100"), quotes[0].price_rub)
        self.assertEqual(Decimal("6000"), quotes[-1].price_rub)

    async def test_non_owner_cannot_manage_wallet(self) -> None:
        service = AufWalletService(_FakeRepository(), _FakeRuntimeService())
        with self.assertRaises(AufWalletAccessError):
            await service.grant(
                workspace_id=7,
                amount_auf=40,
                actor_user_id=77,
                comment="test",
            )


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLAufWalletTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        self.repository = AufWalletRepository(self.database)
        self.service = AufWalletService(self.repository, _FakeRuntimeService())
        await self._reset()

    async def asyncTearDown(self) -> None:
        await self._reset()
        await self.database.close()

    async def _reset(self) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                "DELETE FROM auf_wallet_entries WHERE workspace_id = $1::BIGINT",
                DEFAULT_WORKSPACE_ID,
            )
            await connection.execute(
                """
                INSERT INTO auf_wallets (
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

    async def test_grant_is_idempotent_and_ledger_backed(self) -> None:
        for _ in range(2):
            await self.service.grant(
                workspace_id=DEFAULT_WORKSPACE_ID,
                amount_auf=40,
                actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
                comment="Стартовый пакет",
                idempotency_key="test:wallet:grant:40",
            )
        overview = await self.repository.overview(DEFAULT_WORKSPACE_ID)
        self.assertEqual(auf_to_units(40), overview.wallet.available_units)
        self.assertEqual(1, len(overview.recent_entries))
        self.assertEqual("test:wallet:grant:40", overview.recent_entries[0].idempotency_key)

    async def test_manual_debit_cannot_make_balance_negative(self) -> None:
        await self.service.grant(
            workspace_id=DEFAULT_WORKSPACE_ID,
            amount_auf=1,
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            comment="test",
            idempotency_key="test:wallet:grant:1",
        )
        with self.assertRaises(AufInsufficientBalance):
            await self.service.manual_debit(
                workspace_id=DEFAULT_WORKSPACE_ID,
                amount_auf=2,
                actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
                comment="too much",
                idempotency_key="test:wallet:debit:2",
            )

    async def test_stell_can_freeze_and_unfreeze_wallet(self) -> None:
        frozen = await self.service.set_frozen(
            workspace_id=DEFAULT_WORKSPACE_ID,
            frozen=True,
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
        )
        self.assertIs(AufWalletStatus.FROZEN, frozen.status)
        active = await self.service.set_frozen(
            workspace_id=DEFAULT_WORKSPACE_ID,
            frozen=False,
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
        )
        self.assertIs(AufWalletStatus.ACTIVE, active.status)


if __name__ == "__main__":
    unittest.main()
