from __future__ import annotations

import os
import unittest
from decimal import Decimal

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import AITaskRequest
from velvet_bot.domains.media_generation import KIE_GENERATION_TASK_TYPE
from velvet_bot.domains.meow_wallet import (
    MeowChargedTaskQueueService,
    MeowInsufficientBalance,
    MeowPricingRepository,
    MeowWalletFrozen,
    MeowWalletRepository,
    MeowWalletService,
    auf_to_units,
)
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID


class _FakeRuntimeService:
    async def require_workspace_access(self, *, workspace_id, actor_user_id):
        return None


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLMeowTaskChargingTests(unittest.IsolatedAsyncioTestCase):
    _OWNER_ID = 799_101

    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        self.wallets = MeowWalletRepository(self.database)
        self.wallet_service = MeowWalletService(
            self.wallets,
            _FakeRuntimeService(),
        )
        self.pricing = MeowPricingRepository(self.database)
        self.queue = MeowChargedTaskQueueService(self.database)
        await self._reset()

    async def asyncTearDown(self) -> None:
        await self._reset()
        await self.database.close()

    async def _reset(self) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                "DELETE FROM ai_tasks WHERE dedupe_key LIKE 'test:meow-charge:%'"
            )
            await connection.execute(
                "DELETE FROM meow_wallet_entries WHERE workspace_id = $1::BIGINT",
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

    def _request(
        self,
        *,
        key: str,
        model: str = "nano_banana_2",
        resolution: str = "1K",
        duration: int = 6,
        audio: bool = False,
        references: int = 0,
        created_by: int | None = None,
    ) -> AITaskRequest:
        return AITaskRequest(
            scope=AIBudgetScope.VISION,
            task_type=KIE_GENERATION_TASK_TYPE,
            payload={
                "request": {
                    "model": model,
                    "input_mode": "photo_text",
                    "prompt": "test",
                    "references": [
                        {
                            "telegram_file_id": f"file-{index}",
                            "source": "upload",
                        }
                        for index in range(references)
                    ],
                    "content_mode": "mature",
                    "aspect_ratio": "9:16",
                    "resolution": resolution,
                    "duration_seconds": duration,
                    "output_format": "png",
                    "mode": "normal",
                    "extra_input": {"generate_audio": audio},
                },
                "workspace_id": DEFAULT_WORKSPACE_ID,
                "user_id": created_by or self._OWNER_ID,
            },
            priority=40,
            dedupe_key=f"test:meow-charge:{key}",
            max_attempts=3,
            created_by=created_by or self._OWNER_ID,
            estimated_cost_rub=Decimal("0"),
        )

    async def _grant(self, amount: Decimal | str | int) -> None:
        await self.wallet_service.grant(
            workspace_id=DEFAULT_WORKSPACE_ID,
            amount_auf=amount,
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            comment="test funding",
            idempotency_key=f"test:meow-charge:grant:{amount}",
        )

    async def test_price_catalog_matches_approved_auf_values(self) -> None:
        cases = (
            (self._request(key="quote-nb2").payload, Decimal("1")),
            (
                self._request(
                    key="quote-nbp",
                    model="nano_banana_pro",
                    resolution="4K",
                ).payload,
                Decimal("1.5"),
            ),
            (
                self._request(
                    key="quote-seedream",
                    model="seedream_5_pro",
                    resolution="1K",
                    references=5,
                ).payload,
                Decimal("4.75"),
            ),
            (
                self._request(
                    key="quote-seedance",
                    model="seedance_15_pro_video",
                    resolution="720p",
                    duration=5,
                    audio=True,
                ).payload,
                Decimal("8.75"),
            ),
            (
                self._request(
                    key="quote-wan",
                    model="wan_26_image_to_video",
                    resolution="1080p",
                    duration=5,
                ).payload,
                Decimal("30"),
            ),
        )
        for payload, expected in cases:
            with self.subTest(expected=expected):
                quote = await self.pricing.quote(payload)
                self.assertEqual(expected, quote.quoted_auf)

    async def test_enqueue_reserves_once_and_success_captures(self) -> None:
        await self._grant(10)
        request = self._request(key="capture")
        first = await self.queue.enqueue(request)
        second = await self.queue.enqueue(request)
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.task.id, second.task.id)

        overview = await self.wallets.overview(DEFAULT_WORKSPACE_ID)
        self.assertEqual(auf_to_units(9), overview.wallet.available_units)
        self.assertEqual(auf_to_units(1), overview.wallet.reserved_units)

        async with self.database.acquire() as connection:
            await connection.execute(
                "UPDATE ai_tasks SET status = 'success', updated_at = NOW() WHERE id = $1::UUID",
                first.task.id,
            )
            charge = await connection.fetchrow(
                "SELECT status, captured_units, refunded_units FROM meow_task_charges WHERE task_id = $1::UUID",
                first.task.id,
            )
        self.assertIsNotNone(charge)
        assert charge is not None
        self.assertEqual("captured", str(charge["status"]))
        self.assertEqual(auf_to_units(1), int(charge["captured_units"]))
        self.assertEqual(0, int(charge["refunded_units"]))

        overview = await self.wallets.overview(DEFAULT_WORKSPACE_ID)
        self.assertEqual(auf_to_units(9), overview.wallet.available_units)
        self.assertEqual(0, overview.wallet.reserved_units)

    async def test_terminal_error_refunds_full_reserve(self) -> None:
        await self._grant(2)
        result = await self.queue.enqueue(self._request(key="refund"))
        async with self.database.acquire() as connection:
            await connection.execute(
                "UPDATE ai_tasks SET status = 'error', updated_at = NOW() WHERE id = $1::UUID",
                result.task.id,
            )
            charge_status = await connection.fetchval(
                "SELECT status FROM meow_task_charges WHERE task_id = $1::UUID",
                result.task.id,
            )
        self.assertEqual("refunded", str(charge_status))
        overview = await self.wallets.overview(DEFAULT_WORKSPACE_ID)
        self.assertEqual(auf_to_units(2), overview.wallet.available_units)
        self.assertEqual(0, overview.wallet.reserved_units)

    async def test_cancelled_task_releases_full_reserve(self) -> None:
        await self._grant(2)
        result = await self.queue.enqueue(self._request(key="release"))
        async with self.database.acquire() as connection:
            await connection.execute(
                "UPDATE ai_tasks SET status = 'cancelled', updated_at = NOW() WHERE id = $1::UUID",
                result.task.id,
            )
            charge_status = await connection.fetchval(
                "SELECT status FROM meow_task_charges WHERE task_id = $1::UUID",
                result.task.id,
            )
        self.assertEqual("released", str(charge_status))
        overview = await self.wallets.overview(DEFAULT_WORKSPACE_ID)
        self.assertEqual(auf_to_units(2), overview.wallet.available_units)
        self.assertEqual(0, overview.wallet.reserved_units)

    async def test_insufficient_balance_rolls_back_task_creation(self) -> None:
        request = self._request(key="insufficient")
        with self.assertRaises(MeowInsufficientBalance):
            await self.queue.enqueue(request)
        async with self.database.acquire() as connection:
            task_count = await connection.fetchval(
                "SELECT COUNT(*) FROM ai_tasks WHERE dedupe_key = $1::VARCHAR",
                request.dedupe_key,
            )
        self.assertEqual(0, int(task_count or 0))

    async def test_frozen_wallet_rejects_task_without_orphan(self) -> None:
        await self._grant(2)
        await self.wallet_service.set_frozen(
            workspace_id=DEFAULT_WORKSPACE_ID,
            frozen=True,
            actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
        )
        request = self._request(key="frozen")
        with self.assertRaises(MeowWalletFrozen):
            await self.queue.enqueue(request)
        async with self.database.acquire() as connection:
            task_count = await connection.fetchval(
                "SELECT COUNT(*) FROM ai_tasks WHERE dedupe_key = $1::VARCHAR",
                request.dedupe_key,
            )
        self.assertEqual(0, int(task_count or 0))

    async def test_stell_task_bypasses_auf_wallet(self) -> None:
        result = await self.queue.enqueue(
            self._request(
                key="stell",
                created_by=GLOBAL_WORKSPACE_CREATOR_ID,
            )
        )
        self.assertTrue(result.created)
        async with self.database.acquire() as connection:
            charge_count = await connection.fetchval(
                "SELECT COUNT(*) FROM meow_task_charges WHERE task_id = $1::UUID",
                result.task.id,
            )
        self.assertEqual(0, int(charge_count or 0))


if __name__ == "__main__":
    unittest.main()
