from __future__ import annotations

import asyncio
import os
import unittest
from datetime import date
from decimal import Decimal

from velvet_bot.core.ai_budget import AIBudgetPolicy, AIBudgetScope
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import (
    AIBudgetExceeded,
    AIBudgetWarning,
    AIProviderResult,
    AIRequestContext,
    AIRequestExecutor,
    AIUsageRepository,
    AIUsageService,
)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class AIUsageRepositoryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database.acquire() as connection:
            await connection.execute(
                "TRUNCATE ai_usage_events, ai_tasks RESTART IDENTITY CASCADE"
            )
            await connection.execute(
                """UPDATE ai_runtime_state
                   SET paused=FALSE,pause_reason=NULL,updated_by=NULL,
                       warning_month=NULL,warning_percent=NULL,updated_at=NOW()
                   WHERE singleton_id=1"""
            )
        self.repository = AIUsageRepository(self.database)
        self.policy = AIBudgetPolicy(
            enabled=True,
            daily_limit_rub=Decimal("100"),
            monthly_limit_rub=Decimal("100"),
            max_request_rub=Decimal("80"),
            hermes_reserve_rub=Decimal("20"),
        )
        self.service = AIUsageService(
            self.repository,
            self.policy,
            budget_timezone="UTC",
        )

    async def asyncTearDown(self) -> None:
        await self.database.close()

    @staticmethod
    def _context(
        *,
        scope: AIBudgetScope = AIBudgetScope.VISION,
        cost: str = "10",
        operation: str = "analyze-image",
    ) -> AIRequestContext:
        return AIRequestContext(
            scope=scope,
            provider="test-provider",
            model="test-model",
            operation=operation,
            estimated_cost_rub=Decimal(cost),
            user_id=100,
            chat_id=200,
            metadata={"test": True},
        )

    async def test_complete_replaces_reservation_with_actual_usage(self) -> None:
        reservation = await self.service.reserve(self._context(cost="10"))
        await self.repository.complete(
            request_id=reservation.request_id,
            actual_cost_rub=Decimal("6.75"),
            input_tokens=1200,
            output_tokens=300,
            latency_ms=450,
        )

        totals = await self.service.totals()
        self.assertEqual(Decimal("6.7500"), totals.today_rub)
        self.assertEqual(Decimal("0"), totals.reserved_today_rub)
        events = await self.repository.recent_events(limit=1)
        self.assertEqual("success", events[0]["status"])
        self.assertEqual(1200, events[0]["input_tokens"])
        self.assertEqual(300, events[0]["output_tokens"])

    async def test_regular_requests_cannot_spend_hermes_reserve(self) -> None:
        await self.service.reserve(self._context(cost="75"))
        with self.assertRaisesRegex(AIBudgetExceeded, "резерв Hermes"):
            await self.service.reserve(self._context(cost="10"))

        hermes = await self.service.reserve(
            self._context(
                scope=AIBudgetScope.HERMES,
                cost="10",
                operation="incident-analysis",
            )
        )
        self.assertEqual(AIBudgetScope.HERMES, hermes.context.scope)

    async def test_concurrent_reservations_are_serialized_by_postgres(self) -> None:
        policy = AIBudgetPolicy(
            enabled=True,
            daily_limit_rub=Decimal("15"),
            monthly_limit_rub=Decimal("15"),
            max_request_rub=Decimal("15"),
            hermes_reserve_rub=Decimal("0"),
        )
        service = AIUsageService(self.repository, policy, budget_timezone="UTC")
        results = await asyncio.gather(
            service.reserve(self._context(cost="10")),
            service.reserve(self._context(cost="10")),
            return_exceptions=True,
        )
        allowed = [item for item in results if not isinstance(item, BaseException)]
        denied = [item for item in results if isinstance(item, AIBudgetExceeded)]
        self.assertEqual(1, len(allowed))
        self.assertEqual(1, len(denied))

    async def test_pause_blocks_requests_until_resume(self) -> None:
        await self.service.pause(reason="maintenance", updated_by=100)
        with self.assertRaisesRegex(AIBudgetExceeded, "maintenance"):
            await self.service.reserve(self._context())
        status = await self.service.status()
        self.assertTrue(status.paused)
        self.assertEqual("maintenance", status.pause_reason)
        self.assertEqual(100, status.updated_by)

        await self.service.resume(updated_by=100)
        reservation = await self.service.reserve(self._context())
        self.assertIsNotNone(reservation.request_id)

    async def test_executor_persists_successful_provider_usage(self) -> None:
        executor: AIRequestExecutor[str] = AIRequestExecutor(self.service)

        async def provider_call() -> AIProviderResult[str]:
            return AIProviderResult(
                value="analysis",
                input_tokens=1500,
                output_tokens=500,
                actual_cost_rub=Decimal("3.25"),
            )

        value = await executor.execute(
            context=self._context(cost="5"),
            operation=provider_call,
        )
        self.assertEqual("analysis", value)
        events = await self.repository.recent_events(limit=1)
        self.assertEqual("success", events[0]["status"])
        self.assertEqual(Decimal("3.2500"), events[0]["actual_cost_rub"])

    async def test_budget_warning_is_sent_once_per_threshold(self) -> None:
        warnings: list[AIBudgetWarning] = []

        async def warning_handler(warning: AIBudgetWarning) -> None:
            warnings.append(warning)

        service = AIUsageService(
            self.repository,
            self.policy,
            budget_timezone="UTC",
            warning_handler=warning_handler,
        )
        executor: AIRequestExecutor[str] = AIRequestExecutor(service)

        async def seventy_rubles() -> AIProviderResult[str]:
            return AIProviderResult(value="first", actual_cost_rub=Decimal("70"))

        async def five_rubles() -> AIProviderResult[str]:
            return AIProviderResult(value="second", actual_cost_rub=Decimal("5"))

        await executor.execute(
            context=self._context(cost="70", operation="first"),
            operation=seventy_rubles,
        )
        await executor.execute(
            context=self._context(cost="5", operation="second"),
            operation=five_rubles,
        )

        self.assertEqual(1, len(warnings))
        self.assertEqual(70, warnings[0].threshold_percent)
        state = await self.repository.runtime_state()
        self.assertEqual(70, state["warning_percent"])

    async def test_warning_claim_advances_and_resets_for_new_month(self) -> None:
        july = date(2026, 7, 1)
        august = date(2026, 8, 1)
        self.assertTrue(
            await self.repository.claim_budget_warning(
                period_start=july,
                threshold_percent=70,
            )
        )
        self.assertFalse(
            await self.repository.claim_budget_warning(
                period_start=july,
                threshold_percent=70,
            )
        )
        self.assertTrue(
            await self.repository.claim_budget_warning(
                period_start=july,
                threshold_percent=85,
            )
        )
        self.assertTrue(
            await self.repository.claim_budget_warning(
                period_start=august,
                threshold_percent=70,
            )
        )


if __name__ == "__main__":
    unittest.main()
