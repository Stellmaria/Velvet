from __future__ import annotations

import asyncio
import io
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from PIL import Image

from velvet_bot.domains.ai_usage import AITokenPricing
from velvet_bot.domains.vision_routing.client import MeteredVisionClient
from velvet_bot.domains.vision_routing.models import (
    VisionProviderAnalysis,
    VisionRoute,
    VisionRouteConfig,
)
from velvet_bot.services.typed_quality_vision import TypedQualityVisionClient
from velvet_bot.domains.vision_routing.failures import (
    VisionFailureKind,
    VisionOutOfMemoryError,
    VisionSchemaError,
    VisionTimeoutError,
    VisionTransportError,
    classify_http_failure,
    failure_kind,
    is_full_image_retryable,
    is_permanent_vision_failure,
)


class _UnusedExecutor:
    async def execute(self, **kwargs: object) -> object:
        raise AssertionError(f"executor not expected: {kwargs}")


def _client(*, max_attempts: int = 5) -> MeteredVisionClient:
    return MeteredVisionClient(
        config=VisionRouteConfig(
            route=VisionRoute.FLASH,
            provider="openai_compatible",
            base_url="https://vision.example/v1",
            model="main-vl",
            api_key=None,
            timeout_seconds=30,
            max_attempts=max_attempts,
            pricing=AITokenPricing(
                input_rub_per_million=Decimal("0"),
                output_rub_per_million=Decimal("0"),
            ),
            prompt_version=1,
            schema_version=1,
        ),
        executor=_UnusedExecutor(),  # type: ignore[arg-type]
    )


def _analysis() -> VisionProviderAnalysis:
    return VisionProviderAnalysis(
        profile={"confidence": 90},
        provider="openai_compatible",
        model="main-vl",
        route=VisionRoute.FLASH,
        input_tokens=10,
        output_tokens=5,
        usage_reported=True,
    )


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 24), (80, 90, 100)).save(output, format="JPEG")
    return output.getvalue()


class TypedVisionFailureTests(unittest.IsolatedAsyncioTestCase):
    def test_http_failures_are_typed(self) -> None:
        timeout = classify_http_failure(status=504, detail="Local VL runtime timed out")
        oom = classify_http_failure(status=500, detail="model requires more system memory")
        transient = classify_http_failure(status=503, detail="service unavailable")

        self.assertIsInstance(timeout, VisionTimeoutError)
        self.assertEqual(VisionFailureKind.TIMEOUT, failure_kind(timeout))
        self.assertFalse(is_full_image_retryable(timeout))
        self.assertIsInstance(oom, VisionOutOfMemoryError)
        self.assertTrue(is_permanent_vision_failure(oom))
        self.assertIsInstance(transient, VisionTransportError)
        self.assertTrue(is_full_image_retryable(transient))

    async def test_transport_gets_at_most_one_full_image_retry(self) -> None:
        client = _client(max_attempts=5)
        client._request_once = AsyncMock(  # type: ignore[method-assign]
            side_effect=[VisionTransportError("temporary"), _analysis()]
        )

        result = await client._analyze_with_attempts(b"jpeg")

        self.assertEqual("main-vl", result.model)
        self.assertEqual(2, client._request_once.await_count)  # type: ignore[attr-defined]

    async def test_timeout_is_not_automatically_replayed_with_image(self) -> None:
        client = _client(max_attempts=5)
        client._request_once = AsyncMock(  # type: ignore[method-assign]
            side_effect=VisionTimeoutError("300 second timeout")
        )

        with self.assertRaises(VisionTimeoutError):
            await client._analyze_with_attempts(b"jpeg")

        self.assertEqual(1, client._request_once.await_count)  # type: ignore[attr-defined]

    async def test_oom_and_schema_failures_are_terminal_for_image(self) -> None:
        for error in (
            VisionOutOfMemoryError("oom"),
            VisionSchemaError("bad structured output"),
        ):
            client = _client(max_attempts=5)
            client._request_once = AsyncMock(side_effect=error)  # type: ignore[method-assign]
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)):
                    await client._analyze_with_attempts(b"jpeg")
                self.assertEqual(1, client._request_once.await_count)  # type: ignore[attr-defined]

    async def test_cancellation_propagates_without_retry(self) -> None:
        client = _client(max_attempts=5)
        client._request_once = AsyncMock(side_effect=asyncio.CancelledError())  # type: ignore[method-assign]

        with self.assertRaises(asyncio.CancelledError):
            await client._analyze_with_attempts(b"jpeg")

        self.assertEqual(1, client._request_once.await_count)  # type: ignore[attr-defined]
        self.assertEqual(VisionFailureKind.CANCELLED, failure_kind(asyncio.CancelledError()))

    async def test_quality_invalid_schema_uses_one_http_image_request(self) -> None:
        client = TypedQualityVisionClient(
            provider="ollama",
            base_url="http://vision-runtime:11434",
            model="qwen",
            api_key=None,
            timeout_seconds=30,
        )
        payload = {
            "message": {"content": "not json", "thinking": ""},
            "done_reason": "stop",
            "eval_count": 12,
        }
        with patch(
            "velvet_bot.typed_quality_vision.post_vision_json",
            new=AsyncMock(return_value=payload),
        ) as post:
            with self.assertRaises(VisionSchemaError):
                await client.analyze(_image_bytes())

        post.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
