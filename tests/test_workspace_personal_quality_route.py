from __future__ import annotations

import asyncio
import base64
import io
import json
import unittest
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from PIL import Image

from velvet_bot.ai_quality import build_quality_vision_contract
from velvet_bot.domains.ai_usage import AIRequestExecutor
from velvet_bot.domains.vision_routing.client import MeteredVisionClient
from velvet_bot.domains.vision_routing.models import (
    VisionCascadeResult,
    VisionProviderAnalysis,
    VisionRoute,
    VisionRouteConfig,
)
from velvet_bot.domains.vision_routing.router import VisionCascadeRouter
from velvet_bot.services.workspace_qwen_quality import WorkspaceQwenQualityService


def _image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


class _UnusedExecutor:
    async def execute(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("Provider execution must be skipped on cache hit")


class _CacheOnlyClient:
    route = VisionRoute.FLASH
    provider = "openai_compatible"
    model = "cloud-quality"
    schema_version = 1
    prompt_version = 1
    model_digest = None
    pricing = cast(Any, object())
    _config = SimpleNamespace(timeout_seconds=60, max_attempts=2)

    async def analyze(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("Provider execution must be skipped on cache hit")


class _QualityCache:
    def __init__(self) -> None:
        self.payload = {
            "quality_score": 91,
            "confidence": 94,
            "verdict": "ready",
            "summary_ru": "Кэшированный результат",
            "critical_issues": [],
            "warnings": [],
            "strengths": ["Чёткая композиция"],
            "uncertain_areas": [],
            "checks": {},
        }

    async def get_cache(self, *_args: object, **_kwargs: object) -> object:
        return SimpleNamespace(
            payload=self.payload,
            provider="cloud-pro",
            model="pro-model",
            route=VisionRoute.PRO,
            confidence=94,
            usage_event_id=42,
            prompt_version=1,
            schema_version=1,
        )

    async def put_cache(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("Cache must not be rewritten on a cache hit")


class _WorkspaceRepository:
    def __init__(self) -> None:
        self.completed: dict[str, object] | None = None
        self.failed: dict[str, object] | None = None

    async def claim_next(self) -> object:
        return SimpleNamespace(
            workspace_id=7,
            media_id=41,
            telegram_file_id="telegram-file",
            preview_file_id=None,
            mime_type="image/jpeg",
        )

    async def complete(self, **kwargs: object) -> None:
        self.completed = dict(kwargs)

    async def fail(self, **kwargs: object) -> None:
        self.failed = dict(kwargs)


class _WorkspaceRouter:
    async def analyze(self, source: bytes, **kwargs: object) -> VisionCascadeResult:
        self.source = source
        self.kwargs = dict(kwargs)
        return VisionCascadeResult(
            payload={
                "quality_score": 88,
                "confidence": 92,
                "verdict": "ready",
                "summary_ru": "Готово",
                "critical_issues": [],
                "warnings": [],
                "strengths": [],
                "uncertain_areas": [],
                "checks": {},
            },
            route=VisionRoute.FLASH,
            provider="local_openai_compatible",
            model="qwen",
            model_digest="digest",
            schema_version=1,
            prompt_version=1,
            confidence=92,
            cache_hit=False,
            usage_event_id=123,
            execution_location="local",
            monetary_cost_rub=0.0,
            fallback_used=False,
            fallback_reason=None,
        )


class _TelegramFile:
    file_path = "photos/test.jpg"


class _TelegramBot:
    async def get_file(self, _file_id: str) -> _TelegramFile:
        return _TelegramFile()

    async def download_file(self, _file_path: str, *, destination: io.BytesIO) -> None:
        destination.write(_image_bytes())


class _DownloadFailureBot:
    async def get_file(self, _file_id: str) -> _TelegramFile:
        return _TelegramFile()

    async def download_file(self, _file_path: str, *, destination: io.BytesIO) -> None:
        del destination
        raise RuntimeError("download failed")


class _EmptyRepository:
    async def claim_next(self) -> None:
        return None


class _NoopDatabase:
    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[object]:
        yield object()


class _UsageExecutor:
    async def execute(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("Not used in body-generation test")


class _UnusedPricing:
    pass


class _WorkspaceTargetRepository:
    def __init__(self) -> None:
        self.ready: dict[str, object] | None = None
        self.error: dict[str, object] | None = None

    async def claim_next(self) -> object:
        return SimpleNamespace(
            workspace_id=8,
            media_id=55,
            telegram_file_id="telegram-target",
            preview_file_id=None,
            mime_type="image/jpeg",
        )

    async def mark_ready(self, **kwargs: object) -> None:
        self.ready = dict(kwargs)

    async def mark_error(self, **kwargs: object) -> None:
        self.error = dict(kwargs)


class PersonalQualityRouteTests(unittest.IsolatedAsyncioTestCase):
    def test_quality_contract_drives_openai_compatible_json_schema(self) -> None:
        contract = build_quality_vision_contract()
        config = VisionRouteConfig(
            route=VisionRoute.FLASH,
            provider="openai_compatible",
            base_url="https://vision.example/v1",
            model="cloud-quality",
            api_key="test-key",
            timeout_seconds=60,
            max_attempts=2,
            pricing=cast(Any, object()),
            prompt_version=1,
            schema_version=contract.schema_version,
        )
        client = MeteredVisionClient(
            config=config,
            executor=cast(AIRequestExecutor[VisionProviderAnalysis], _UnusedExecutor()),
            contract=contract,
        )

        body = client._request_body("encoded")

        self.assertEqual(contract.prompt, body["messages"][0]["content"][0]["text"])
        response_format = cast(dict[str, Any], body["response_format"])
        json_schema = cast(dict[str, Any], response_format["json_schema"])
        self.assertEqual("velvet_personal_quality_flash", json_schema["name"])
        self.assertEqual(contract.schema, json_schema["schema"])
        self.assertEqual(512, body["max_tokens"])

    async def test_personal_quality_cache_hit_skips_provider_execution(self) -> None:
        flash = _CacheOnlyClient()
        cache = _QualityCache()
        router = VisionCascadeRouter(
            flash=cast(Any, flash),
            repository=cast(Any, cache),
            analysis_type="personal-quality",
            schema_version=1,
        )

        result = await router.analyze(_image_bytes())

        self.assertTrue(result.cache_hit)
        self.assertEqual("cloud-pro", result.provider)
        self.assertEqual("pro-model", result.model)
        self.assertEqual(VisionRoute.PRO, result.route)
        self.assertEqual(cache.payload, result.payload)

    async def test_workspace_service_persists_router_metadata(self) -> None:
        repository = _WorkspaceRepository()
        router = _WorkspaceRouter()
        service = WorkspaceQwenQualityService(
            bot=cast(Any, _TelegramBot()),
            repository=cast(Any, repository),
            client=cast(Any, router),
            max_attempts=2,
        )

        processed = await service.process_once()

        self.assertEqual(1, processed)
        self.assertIsNotNone(repository.completed)
        assert repository.completed is not None
        self.assertEqual("local_openai_compatible", repository.completed["provider"])
        self.assertEqual("qwen", repository.completed["model"])
        self.assertEqual("digest", repository.completed["model_digest"])
        self.assertEqual("flash", repository.completed["route"])
        self.assertEqual(123, repository.completed["usage_event_id"])
        self.assertFalse(bool(repository.completed["cache_hit"]))
        self.assertEqual(1, repository.completed["schema_version"])
        self.assertEqual(1, repository.completed["prompt_version"])

    async def test_workspace_service_compensates_download_failure(self) -> None:
        repository = _WorkspaceTargetRepository()
        router = _WorkspaceRouter()
        service = WorkspaceQwenQualityService(
            bot=cast(Any, _DownloadFailureBot()),
            repository=cast(Any, repository),
            client=cast(Any, router),
            max_attempts=2,
        )

        processed = await service.process_once()

        self.assertEqual(0, processed)
        self.assertIsNone(repository.ready)
        self.assertIsNotNone(repository.error)
        assert repository.error is not None
        self.assertEqual(8, repository.error["workspace_id"])
        self.assertEqual(55, repository.error["media_id"])
        self.assertEqual(2, repository.error["max_attempts"])
        self.assertIn("download failed", str(repository.error["error"]))

    async def test_workspace_service_returns_zero_when_queue_is_empty(self) -> None:
        service = WorkspaceQwenQualityService(
            bot=cast(Any, _TelegramBot()),
            repository=cast(Any, _EmptyRepository()),
            client=cast(Any, _WorkspaceRouter()),
            max_attempts=2,
        )

        processed = await service.process_once()

        self.assertEqual(0, processed)


if __name__ == "__main__":
    unittest.main()
