from __future__ import annotations

import unittest
from decimal import Decimal

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import (
    AIProviderResult,
    AIRequestContext,
    AIRequestExecutor,
    AITaskRequest,
)
from velvet_bot.domains.media_generation.economy_worker import (
    _campaign_runtime,
    _reference_url_failure,
)
from velvet_bot.domains.media_generation.models import (
    KieTaskRecord,
    KieTaskState,
)


class KieCampaignAttemptLimitTests(unittest.TestCase):
    def test_ai_task_accepts_fifty_attempts(self) -> None:
        request = AITaskRequest(
            scope=AIBudgetScope.VISION,
            task_type="media.generate.kie",
            max_attempts=50,
        )
        self.assertEqual(50, request.max_attempts)

    def test_ai_task_rejects_more_than_fifty_attempts(self) -> None:
        with self.assertRaises(ValueError):
            AITaskRequest(
                scope=AIBudgetScope.VISION,
                task_type="media.generate.kie",
                max_attempts=51,
            )

    def test_campaign_runtime_starts_sequential_and_empty(self) -> None:
        runtime = _campaign_runtime({})
        self.assertEqual("economy", runtime["mode"])
        self.assertEqual(0, runtime["provider_attempt_count"])
        self.assertEqual([], runtime["attempt_history"])

    def test_expired_reference_failure_forces_reference_refresh(self) -> None:
        record = KieTaskRecord(
            task_id="task-1",
            state=KieTaskState.FAIL,
            failure_message="Input image URL expired",
        )
        self.assertTrue(_reference_url_failure(record))


class _Reservation:
    pass


class _UsageService:
    def __init__(self) -> None:
        self.failed: list[dict[str, object]] = []

    async def reserve(self, context):
        self.context = context
        return _Reservation()

    async def cancel(self, reservation, *, reason):
        raise AssertionError("cancel should not be called")

    async def complete(self, reservation, result, *, latency_ms):
        raise AssertionError("complete should not be called")

    async def fail(
        self,
        reservation,
        error,
        *,
        latency_ms,
        actual_cost_rub=Decimal("0"),
        input_tokens=0,
        output_tokens=0,
        metadata=None,
    ):
        self.failed.append(
            {
                "error": error,
                "actual_cost_rub": actual_cost_rub,
                "metadata": dict(metadata or {}),
            }
        )


class ChargedFailureAccountingTests(unittest.IsolatedAsyncioTestCase):
    async def test_executor_records_charged_provider_failure(self) -> None:
        service = _UsageService()
        executor = AIRequestExecutor(service)  # type: ignore[arg-type]
        context = AIRequestContext(
            scope=AIBudgetScope.VISION,
            provider="kie",
            model="seedream/5-pro-image-to-image",
            operation="media.generate",
            estimated_cost_rub=Decimal("12.50"),
        )

        async def operation():
            raise RuntimeError("provider generation failed")

        def failure_usage(error):
            return AIProviderResult(
                value=None,
                actual_cost_rub=Decimal("12.50"),
                metadata={"consumed_credits": 25},
            )

        with self.assertRaises(RuntimeError):
            await executor.execute(
                context=context,
                operation=operation,
                failure_usage=failure_usage,
            )

        self.assertEqual(1, len(service.failed))
        self.assertEqual(Decimal("12.50"), service.failed[0]["actual_cost_rub"])
        self.assertEqual(25, service.failed[0]["metadata"]["consumed_credits"])


if __name__ == "__main__":
    unittest.main()
