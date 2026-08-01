from __future__ import annotations

import unittest
from decimal import Decimal
from typing import Any

from velvet_bot.ai_vision import VisionAnalysisError
from velvet_bot.domains.ai_usage import AITokenPricing
from velvet_bot.domains.vision_routing.client import (
    MeteredVisionClient,
    _estimate_input_tokens,
    _extract_provider_content,
    _extract_usage,
)
from velvet_bot.domains.vision_routing.models import (
    VisionProviderAnalysis,
    VisionRoute,
    VisionRouteConfig,
)


class _FakeExecutor:
    def __init__(self) -> None:
        self.context: object | None = None
        self.result: object | None = None

    async def execute(self, *, context: object, operation: Any) -> object:
        self.context = context
        provider_result = await operation()
        self.result = provider_result
        return provider_result.value


class MeteredVisionClientTests(unittest.IsolatedAsyncioTestCase):
    def _client(
        self,
        executor: _FakeExecutor,
        *,
        route: VisionRoute = VisionRoute.FLASH,
        prompt_version: int = 1,
    ) -> MeteredVisionClient:
        return MeteredVisionClient(
            config=VisionRouteConfig(
                route=route,
                provider="openai_compatible",
                base_url="https://example.invalid/v1",
                model=f"{route.value}-model",
                api_key="test-key",
                timeout_seconds=30,
                max_attempts=1,
                pricing=AITokenPricing(
                    input_rub_per_million=Decimal("10"),
                    output_rub_per_million=Decimal("20"),
                ),
                prompt_version=prompt_version,
                schema_version=1,
            ),
            executor=executor,  # type: ignore[arg-type]
        )

    async def test_analyze_prepared_uses_conservative_usage_when_missing(self) -> None:
        executor = _FakeExecutor()
        client = self._client(executor)
        raw = VisionProviderAnalysis(
            profile={"confidence": 82, "series_title_ru": "Тест"},
            provider="openai_compatible",
            model="flash-model",
            route=VisionRoute.FLASH,
            input_tokens=0,
            output_tokens=0,
            usage_reported=False,
        )

        async def fake_analyze(prepared: bytes) -> VisionProviderAnalysis:
            self.assertEqual(b"jpeg-bytes", prepared)
            return raw

        client._analyze_with_attempts = fake_analyze  # type: ignore[method-assign]
        result = await client.analyze_prepared(
            b"jpeg-bytes",
            user_id=10,
            chat_id=20,
        )

        self.assertFalse(result.usage_reported)
        self.assertGreater(result.input_tokens, 0)
        self.assertGreater(result.output_tokens, 0)
        self.assertGreater(result.actual_cost_rub, Decimal("0"))
        self.assertIsNotNone(executor.context)

    async def test_provider_reported_usage_is_preserved(self) -> None:
        executor = _FakeExecutor()
        client = self._client(executor)
        raw = VisionProviderAnalysis(
            profile={"confidence": 91},
            provider="openai_compatible",
            model="flash-model",
            route=VisionRoute.FLASH,
            input_tokens=1500,
            output_tokens=250,
            usage_reported=True,
        )

        async def fake_analyze(prepared: bytes) -> VisionProviderAnalysis:
            return raw

        client._analyze_with_attempts = fake_analyze  # type: ignore[method-assign]
        result = await client.analyze_prepared(b"jpeg")

        self.assertEqual(1500, result.input_tokens)
        self.assertEqual(250, result.output_tokens)
        self.assertEqual(Decimal("0.0200"), result.actual_cost_rub)

    def test_sensitive_request_uses_separate_prompt_and_strict_schema(self) -> None:
        client = self._client(
            _FakeExecutor(),
            route=VisionRoute.SENSITIVE,
            prompt_version=7,
        )

        body = client._request_body("abc")

        prompt = body["messages"][0]["content"][0]["text"]
        response_format = body["response_format"]
        schema = response_format["json_schema"]["schema"]
        self.assertIn("route должен быть sensitive", prompt)
        self.assertEqual("json_schema", response_format["type"])
        self.assertTrue(response_format["json_schema"]["strict"])
        self.assertEqual("sensitive", schema["properties"]["route"]["const"])
        self.assertEqual(1800, body["max_tokens"])

    def test_standard_request_cannot_return_sensitive_content_mode(self) -> None:
        client = self._client(_FakeExecutor(), route=VisionRoute.FLASH)

        schema = client._request_body("abc")["response_format"]["json_schema"]["schema"]

        self.assertEqual("standard", schema["properties"]["route"]["const"])
        self.assertNotIn(
            "explicit_adult",
            schema["properties"]["content_mode"]["enum"],
        )

    def test_extracts_openai_and_ollama_usage(self) -> None:
        self.assertEqual(
            (123, 45, True),
            _extract_usage(
                {"usage": {"prompt_tokens": 123, "completion_tokens": 45}},
                provider="openai_compatible",
            ),
        )
        self.assertEqual(
            (321, 54, True),
            _extract_usage(
                {"prompt_eval_count": 321, "eval_count": 54},
                provider="ollama",
            ),
        )
        self.assertEqual(
            (0, 0, False),
            _extract_usage({}, provider="openai_compatible"),
        )

    def test_extracts_refusal_as_routeable_error(self) -> None:
        with self.assertRaisesRegex(VisionAnalysisError, "provider refusal"):
            _extract_provider_content(
                {
                    "choices": [
                        {"message": {"refusal": "blocked by content policy"}}
                    ]
                },
                provider="openai_compatible",
            )

    def test_input_estimate_is_bounded(self) -> None:
        small = _estimate_input_tokens(b"x" * 10)
        large = _estimate_input_tokens(b"x" * 10_000_000)
        self.assertGreaterEqual(small, 512)
        self.assertGreater(large, small)
        self.assertLessEqual(large, small + 4096)


if __name__ == "__main__":
    unittest.main()
