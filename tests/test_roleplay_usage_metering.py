from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Sequence

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage.models import AIProviderResult, AIRequestContext
from velvet_bot.domains.ai_usage.pricing import AITokenPricing
from velvet_bot.domains.roleplay.client import GeneratedRoleplayText, TextRoleplayClient
from velvet_bot.domains.roleplay.models import RoleplayMessage


def _message(content: str = "Продолжи сцену") -> RoleplayMessage:
    return RoleplayMessage(
        id=1,
        chat_id=100,
        user_id=200,
        role="user",
        content=content,
        created_at=datetime.now(timezone.utc),
    )


class _CapturingExecutor:
    def __init__(self) -> None:
        self.context: AIRequestContext | None = None
        self.result: AIProviderResult[GeneratedRoleplayText] | None = None

    async def execute(self, *, context: AIRequestContext, operation: Any) -> GeneratedRoleplayText:
        self.context = context
        self.result = await operation()
        return self.result.value


class _StubRoleplayClient(TextRoleplayClient):
    def __init__(self, *, payload: dict[str, object], executor: Any) -> None:
        super().__init__(
            provider="openai_compatible",
            base_url="https://provider.example/v1",
            model="roleplay-test",
            api_key="secret",
            timeout_seconds=30,
            max_output_tokens=1000,
            max_attempts=1,
            executor=executor,
            pricing=AITokenPricing(
                input_rub_per_million=Decimal("10"),
                output_rub_per_million=Decimal("20"),
            ),
        )
        self._payload = payload

    def _request_once(
        self,
        instructions: str,
        messages: Sequence[RoleplayMessage],
    ) -> dict[str, Any]:
        return dict(self._payload)


class RoleplayUsageMeteringTests(unittest.IsolatedAsyncioTestCase):
    async def test_reserves_budget_before_provider_and_uses_reported_tokens(self) -> None:
        executor = _CapturingExecutor()
        client = _StubRoleplayClient(
            executor=executor,
            payload={
                "choices": [{"message": {"content": "Ответ модели"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
        )

        generated = await client.generate(
            instructions="Соблюдай канон",
            messages=(_message(),),
        )

        self.assertEqual(generated.text, "Ответ модели")
        self.assertTrue(generated.usage_reported)
        self.assertIsNotNone(executor.context)
        self.assertIsNotNone(executor.result)
        assert executor.context is not None
        assert executor.result is not None
        self.assertEqual(executor.context.scope, AIBudgetScope.ROLEPLAY)
        self.assertEqual(executor.context.user_id, 200)
        self.assertEqual(executor.context.chat_id, 100)
        self.assertGreater(executor.context.estimated_cost_rub, Decimal("0"))
        self.assertEqual(executor.result.input_tokens, 100)
        self.assertEqual(executor.result.output_tokens, 50)
        self.assertEqual(executor.result.actual_cost_rub, Decimal("0.0020"))
        self.assertTrue(executor.result.metadata["provider_reported_usage"])

    async def test_uses_conservative_estimate_when_provider_omits_usage(self) -> None:
        executor = _CapturingExecutor()
        client = _StubRoleplayClient(
            executor=executor,
            payload={"choices": [{"message": {"content": "Длинный ответ модели"}}]},
        )

        generated = await client.generate(
            instructions="Соблюдай канон",
            messages=(_message("Короткая реплика"),),
        )

        self.assertFalse(generated.usage_reported)
        assert executor.result is not None
        self.assertGreater(executor.result.input_tokens, 0)
        self.assertGreater(executor.result.output_tokens, 0)
        self.assertGreater(executor.result.actual_cost_rub, Decimal("0"))
        self.assertFalse(executor.result.metadata["provider_reported_usage"])


if __name__ == "__main__":
    unittest.main()
