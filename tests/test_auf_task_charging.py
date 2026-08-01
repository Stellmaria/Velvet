from __future__ import annotations

import os
import unittest
import uuid
from decimal import Decimal

from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import AITaskRequest
from velvet_bot.domains.auf_wallet import (
    AUF_SCALE,
    AufChargedTaskQueueService,
    AufInsufficientBalance,
    AufPricingRepository,
    AufWalletRepository,
    AufWalletService,
    AufWalletStatus,
)
from velvet_bot.domains.media_generation import KIE_GENERATION_TASK_TYPE


class PostgreSQLAufTaskChargingTests(unittest.IsolatedAsyncioTestCase):
    _OWNER_ID = 7221553045
    _USER_ID = 820000001

    async def asyncSetUp(self) -> None:
        database_url = os.getenv("TEST_DATABASE_URL")
        if not database_url:
            self.skipTest("TEST_DATABASE_URL is not configured")
        self.database = Database(database_url)
        await self.database.connect()
        await self.database.run_migrations()
        self.queue = AufChargedTaskQueueService(self.database)
        self.pricing = AufPricingRepository(self.database)
        self.wallet_repository = AufWalletRepository(self.database)
        self.wallet_service = AufWalletService(
            self.wallet_repository,
            global_owner_id=self._OWNER_ID,
        )
        self.workspace_id = await self._create_workspace()

    async def asyncTearDown(self) -> None:
        if not hasattr(self, "database"):
            return
        async with self.database.acquire() as connection:
            await connection.execute(
                "DELETE FROM workspaces WHERE id = $1::BIGINT",
                self.workspace_id,
            )
        await self.database.close()

    async def _create_workspace(self) -> int:
        suffix = uuid.uuid4().hex[:10]
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspaces (
                    name, slug, is_system, is_active, created_by_user_id
                )
                VALUES ($1::VARCHAR, $2::VARCHAR, FALSE, TRUE, $3::BIGINT)
                RETURNING id
                """,
                f"Auf task charging {suffix}",
                f"auf-task-charging-{suffix}",
                self._USER_ID,
            )
            assert row is not None
            await connection.execute(
                """
                INSERT INTO workspace_members (workspace_id, user_id, role)
                VALUES ($1::BIGINT, $2::BIGINT, 'owner')
                """,
                int(row["id"]),
                self._USER_ID,
            )
            return int(row["id"])

    def _request(
        self,
        key: str | None = None,
        *,
        model: str = "nano_banana_2",
        resolution: str = "1K",
        duration: int = 6,
        references: int = 0,
        audio: bool = False,
        created_by: int | None = None,
    ) -> AITaskRequest:
        identity = key or uuid.uuid4().hex
        return AITaskRequest(
            scope="vision",
            task_type=KIE_GENERATION_TASK_TYPE,
            payload={
                "workspace_id": self.workspace_id,
                "user_id": created_by or self._USER_ID,
                "request": {
                    "model": model,
                    "input_mode": "text",
                    "prompt": "test prompt",
                    "references": [{} for _ in range(references)],
                    "content_mode": "mature",
                    "aspect_ratio": "1:1",
                    "resolution": resolution,
                    "duration_seconds": duration,
                    "output_format": "png",
                    "mode": "normal",
                    "extra_input": {"generate_audio": audio},
                },
            },
            priority=40,
            max_attempts=3,
            idempotency_key=f"auf-task-charging:{identity}",
            created_by=created_by or self._USER_ID,
            estimated_cost_rub=Decimal("1"),
        )

    async def _grant(self, amount: Decimal = Decimal("100")) -> None:
        await self.wallet_service.grant(
            workspace_id=self.workspace_id,
            amount_auf=amount,
            actor_user_id=self._OWNER_ID,
            comment="test",
            idempotency_key=f"grant:{uuid.uuid4()}",
        )

    async def test_enqueue_reserves_once_and_success_captures(self) -> None:
        await self._grant()
        request = self._request()
        quote = await self.pricing.quote(request.payload)
        result = await self.queue.enqueue(request)
        duplicate = await self.queue.enqueue(request)
        self.assertTrue(result.created)
        self.assertFalse(duplicate.created)
        wallet = await self.wallet_repository.get_wallet(self.workspace_id)
        self.assertEqual(quote.quoted_units, wallet.reserved_units)
        self.assertEqual(100 * AUF_SCALE - quote.quoted_units, wallet.available_units)

        await self.wallet_service.capture_for_task(
            task_id=result.task.id,
            actual_cost_usd=quote.provider_cost_usd,
        )
        wallet = await self.wallet_repository.get_wallet(self.workspace_id)
        self.assertEqual(0, wallet.reserved_units)
        self.assertEqual(100 * AUF_SCALE - quote.quoted_units, wallet.available_units)

    async def test_price_catalog_uses_provider_plus_thirty_whole_values(self) -> None:
        cases = (
            (self._request(key="quote-nb2").payload, Decimal("1")),
            (
                self._request(
                    key="quote-nbp",
                    model="nano_banana_pro",
                    resolution="4K",
                ).payload,
                Decimal("3"),
            ),
            (
                self._request(
                    key="quote-seedream",
                    model="seedream_5_pro",
                    resolution="1K",
                    references=5,
                ).payload,
                Decimal("5"),
            ),
            (
                self._request(
                    key="quote-seedance",
                    model="seedance_15_pro_video",
                    resolution="720p",
                    duration=5,
                    audio=True,
                ).payload,
                Decimal("9"),
            ),
            (
                self._request(
                    key="quote-wan",
                    model="wan_26_image_to_video",
                    resolution="1080p",
                    duration=5,
                ).payload,
                Decimal("29"),
            ),
        )
        for payload, expected in cases:
            with self.subTest(expected=expected):
                quote = await self.pricing.quote(payload)
                self.assertEqual(expected, quote.quoted_auf)
                self.assertEqual(0, quote.quoted_units % AUF_SCALE)
                self.assertGreaterEqual(
                    quote.minimum_revenue_usd,
                    quote.target_retail_usd,
                )

    async def test_individual_markup_reprices_only_target_user(self) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO telegram_users (user_id, first_name)
                VALUES ($1::BIGINT, 'Pricing test')
                ON CONFLICT (user_id) DO NOTHING
                """,
                self._OWNER_ID,
            )
        baseline = await self.pricing.quote(
            self._request(
                key="individual-baseline",
                model="nano_banana_pro",
                resolution="1K",
                created_by=self._USER_ID,
            ).payload
        )
        policy = await self.pricing.set_user_markup(
            user_id=self._OWNER_ID,
            markup_percent=Decimal("100"),
            actor_user_id=self._OWNER_ID,
        )
        self.assertEqual(Decimal("100.00"), policy.effective_markup_percent)
        custom = await self.pricing.quote(
            self._request(
                key="individual-custom",
                model="nano_banana_pro",
                resolution="1K",
                created_by=self._OWNER_ID,
            ).payload
        )
        unaffected = await self.pricing.quote(
            self._request(
                key="individual-unaffected",
                model="nano_banana_pro",
                resolution="1K",
                created_by=self._USER_ID,
            ).payload
        )
        self.assertGreater(custom.quoted_units, baseline.quoted_units)
        self.assertEqual(baseline.quoted_units, unaffected.quoted_units)
        await self.pricing.clear_user_markup(user_id=self._OWNER_ID)

    async def test_insufficient_balance_rolls_back_task_creation(self) -> None:
        request = self._request()
        with self.assertRaises(AufInsufficientBalance):
            await self.queue.enqueue(request)
        async with self.database.acquire() as connection:
            count = await connection.fetchval(
                "SELECT COUNT(*) FROM ai_tasks WHERE idempotency_key = $1::VARCHAR",
                request.idempotency_key,
            )
        self.assertEqual(0, int(count or 0))

    async def test_cancelled_task_releases_full_reserve(self) -> None:
        await self._grant()
        result = await self.queue.enqueue(self._request())
        await self.wallet_service.release_for_task(
            task_id=result.task.id,
            reason="cancelled",
        )
        wallet = await self.wallet_repository.get_wallet(self.workspace_id)
        self.assertEqual(0, wallet.reserved_units)
        self.assertEqual(100 * AUF_SCALE, wallet.available_units)

    async def test_frozen_wallet_rejects_task_without_orphan(self) -> None:
        await self._grant()
        await self.wallet_service.set_status(
            workspace_id=self.workspace_id,
            status=AufWalletStatus.FROZEN,
            actor_user_id=self._OWNER_ID,
            comment="test freeze",
        )
        request = self._request()
        with self.assertRaisesRegex(Exception, "заморожен"):
            await self.queue.enqueue(request)
        async with self.database.acquire() as connection:
            count = await connection.fetchval(
                "SELECT COUNT(*) FROM ai_tasks WHERE idempotency_key = $1::VARCHAR",
                request.idempotency_key,
            )
        self.assertEqual(0, int(count or 0))


if __name__ == "__main__":
    unittest.main()
