from __future__ import annotations

import io
import os
import unittest
from decimal import Decimal
from typing import Any, Mapping, cast
from unittest.mock import AsyncMock

from PIL import Image

from velvet_bot.ai_quality import build_quality_vision_contract
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import AIRequestExecutor
from velvet_bot.domains.vision_routing.client import MeteredVisionClient
from velvet_bot.domains.vision_routing.models import (
    CachedVisionAnalysis,
    VisionCascadeResult,
    VisionProviderAnalysis,
    VisionRoute,
    VisionRouteConfig,
)
from velvet_bot.domains.vision_routing.service import VisionCascadeRouter
from velvet_bot.domains.workspaces.qwen_repository import (
    WorkspaceQwenRepository,
    WorkspaceQwenTarget,
)
from velvet_bot.quality_calibration import CalibrationProfile
from velvet_bot.services.workspace_qwen_quality import WorkspaceQwenQualityService


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 24), (120, 80, 40)).save(output, format="JPEG")
    return output.getvalue()


def _quality_report(*, confidence: int = 91) -> dict[str, object]:
    return {
        "quality_score": 88,
        "confidence": confidence,
        "verdict": "ready",
        "summary_ru": "Явных технических дефектов не обнаружено.",
        "critical_issues": [],
        "warnings": [],
        "strengths": ["Чистый свет"],
        "uncertain_areas": [],
        "checks": {
            key: 90
            for key in (
                "anatomy",
                "hands",
                "face",
                "hair",
                "skin_texture",
                "lighting",
                "exposure",
                "sharpness",
                "background",
                "reflections",
                "composition",
                "compression",
                "text_watermarks",
                "ui_artifacts",
            )
        },
    }


def _inactive_profile() -> CalibrationProfile:
    return CalibrationProfile(
        sample_count=0,
        useful_count=0,
        false_alarm_count=0,
        missed_problem_count=0,
        uncertain_count=0,
        accepted_count=0,
        fix_required_count=0,
        usefulness_rate=0,
        false_alarm_rate=0,
        missed_problem_rate=0,
        ready_min_score=80,
        fix_max_score=40,
        min_confidence=70,
        active=False,
    )


class _UnusedExecutor:
    async def execute(self, **kwargs: object) -> VisionProviderAnalysis:
        raise AssertionError(f"Provider execution was not expected: {kwargs}")


class _CacheOnlyClient:
    def __init__(self) -> None:
        self.route = VisionRoute.FLASH
        self.provider = "cloud-flash"
        self.model = "flash-model"
        self.calls = 0

    async def health(self) -> bool:
        return True

    async def analyze_prepared(self, *args: object, **kwargs: object) -> VisionProviderAnalysis:
        self.calls += 1
        raise AssertionError("Cache hit must not call provider or ledger executor")


class _QualityCache:
    def __init__(self) -> None:
        self.find_calls: list[dict[str, object]] = []

    async def find(self, **kwargs: object) -> CachedVisionAnalysis:
        self.find_calls.append(dict(kwargs))
        return CachedVisionAnalysis(
            cache_id=91,
            content_hash="a" * 64,
            analysis_type="personal-quality:schema-1:standard",
            prompt_version=1,
            route=VisionRoute.PRO,
            provider="cloud-pro",
            model="pro-model",
            profile=_quality_report(confidence=94),
            confidence=94,
            input_tokens=700,
            output_tokens=220,
            actual_cost_rub=Decimal("1.25"),
        )

    async def store(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("Cache hit must not be stored again")


class _RoutedQualityClient:
    provider = "cloud-flash"
    model = "flash-model"
    configured_models = ("flash-model", "pro-model")

    def __init__(self) -> None:
        self.metadata: Mapping[str, object] | None = None

    async def health(self) -> bool:
        return True

    async def analyze(
        self,
        source: bytes,
        **kwargs: object,
    ) -> VisionCascadeResult:
        self.metadata = cast(Mapping[str, object], kwargs.get("metadata"))
        if not source:
            raise AssertionError("Expected image bytes")
        return VisionCascadeResult(
            profile=_quality_report(),
            content_hash="b" * 64,
            route=VisionRoute.PRO,
            provider="cloud-pro",
            model="pro-model",
            confidence=91,
            cache_hit=True,
            attempts=(),
            input_tokens=600,
            output_tokens=200,
            actual_cost_rub=Decimal("0.90"),
        )


class _ServiceRepository:
    def __init__(self) -> None:
        self.target = WorkspaceQwenTarget(
            workspace_id=17,
            media_id=29,
            telegram_file_id="file-id",
            preview_file_id=None,
            mime_type="image/jpeg",
        )
        self.claim: dict[str, object] | None = None
        self.calibration: dict[str, object] | None = None
        self.ready: dict[str, object] | None = None

    async def claim_next(self, **kwargs: object) -> WorkspaceQwenTarget:
        self.claim = dict(kwargs)
        return self.target

    async def calibration_profile(self, **kwargs: object) -> CalibrationProfile:
        self.calibration = dict(kwargs)
        return _inactive_profile()

    async def mark_ready(self, **kwargs: object) -> None:
        self.ready = dict(kwargs)

    async def mark_error(self, **kwargs: object) -> None:
        raise AssertionError(f"Unexpected compensation: {kwargs}")


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
        self.assertEqual(1700, body["max_tokens"])

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
        self.assertEqual(0, flash.calls)
        self.assertEqual(
            "personal-quality:schema-1:standard",
            cache.find_calls[0]["analysis_type"],
        )

    async def test_service_persists_actual_fallback_route_and_workspace_metadata(self) -> None:
        repository = _ServiceRepository()
        routed = _RoutedQualityClient()
        service = WorkspaceQwenQualityService(
            bot=cast(Any, object()),
            repository=cast(Any, repository),
            client=cast(Any, routed),
        )
        service._download_target = AsyncMock(return_value=_image_bytes())  # type: ignore[method-assign]

        processed = await service.process_once()

        self.assertEqual(1, processed)
        self.assertEqual(
            {"provider": "cloud-flash", "model": "flash-model", "max_attempts": 3},
            repository.claim,
        )
        self.assertEqual(
            {"workspace_id": 17, "provider": "cloud-pro", "model": "pro-model"},
            repository.calibration,
        )
        self.assertIsNotNone(repository.ready)
        self.assertEqual("cloud-pro", repository.ready["provider"])
        self.assertEqual("pro-model", repository.ready["model"])
        self.assertEqual(17, routed.metadata["workspace_id"])
        self.assertEqual(29, routed.metadata["media_id"])
        self.assertEqual("personal-quality", routed.metadata["surface"])


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLPersonalQualityRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        self.repository = WorkspaceQwenRepository(self.database)
        self.media_ids: list[int] = []
        await self._cleanup()

    async def asyncTearDown(self) -> None:
        await self._cleanup()
        await self.database.close()

    async def _cleanup(self) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                "DELETE FROM workspaces WHERE slug LIKE 'quality-route-test-%'"
            )
            await connection.execute(
                "DELETE FROM media_files WHERE telegram_file_unique_id LIKE 'quality-route-test-%'"
            )

    async def _workspace(self, suffix: str, *, enabled: bool) -> int:
        async with self.database.acquire() as connection:
            workspace_id = await connection.fetchval(
                """
                INSERT INTO workspaces (slug, name, is_system)
                VALUES ($1::VARCHAR, $2::VARCHAR, FALSE)
                RETURNING id
                """,
                f"quality-route-test-{suffix}",
                f"Quality {suffix}",
            )
            await connection.execute(
                """
                INSERT INTO workspace_settings (workspace_id, qwen_enabled)
                VALUES ($1::BIGINT, $2::BOOLEAN)
                ON CONFLICT (workspace_id) DO UPDATE
                SET qwen_enabled = EXCLUDED.qwen_enabled
                """,
                int(workspace_id),
                bool(enabled),
            )
            await connection.execute(
                """
                INSERT INTO workspace_modules (
                    workspace_id, module_key, is_allowed, is_enabled
                )
                VALUES ($1::BIGINT, 'qwen', TRUE, $2::BOOLEAN)
                ON CONFLICT (workspace_id, module_key) DO UPDATE
                SET is_allowed = TRUE, is_enabled = EXCLUDED.is_enabled
                """,
                int(workspace_id),
                bool(enabled),
            )
        return int(workspace_id)

    async def _media(self, suffix: str) -> int:
        async with self.database.acquire() as connection:
            media_id = await connection.fetchval(
                """
                INSERT INTO media_files (
                    telegram_file_id,
                    telegram_file_unique_id,
                    storage_file_name,
                    media_type,
                    mime_type,
                    file_size
                )
                VALUES (
                    $1::TEXT, $2::TEXT, $3::TEXT,
                    'photo', 'image/jpeg', 1024
                )
                RETURNING id
                """,
                f"quality-route-file-{suffix}",
                f"quality-route-test-{suffix}",
                f"quality-route-test-{suffix}.jpg",
            )
        self.media_ids.append(int(media_id))
        return int(media_id)

    async def test_claim_and_ready_keep_exact_workspace_pair_and_actual_route(self) -> None:
        first = await self._workspace("first", enabled=True)
        second = await self._workspace("second", enabled=False)
        first_media = await self._media("first")
        second_media = await self._media("second")
        async with self.database.acquire() as connection:
            await connection.executemany(
                """
                INSERT INTO workspace_qwen_checks (
                    workspace_id, media_id, status, updated_at
                )
                VALUES ($1::BIGINT, $2::BIGINT, 'pending', NOW())
                """,
                [(first, first_media), (second, second_media)],
            )

        target = await self.repository.claim_next(
            provider="cloud-flash",
            model="flash-model",
            max_attempts=3,
        )

        self.assertIsNotNone(target)
        self.assertEqual((first, first_media), (target.workspace_id, target.media_id))
        await self.repository.mark_ready(
            workspace_id=first,
            media_id=first_media,
            provider="cloud-pro",
            model="pro-model",
            report=cast(dict[str, Any], _quality_report()),
        )
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT status, provider, model
                FROM workspace_qwen_checks
                WHERE workspace_id = $1::BIGINT AND media_id = $2::BIGINT
                """,
                first,
                first_media,
            )
        self.assertEqual(("ready", "cloud-pro", "pro-model"), tuple(row))

        with self.assertRaisesRegex(ValueError, "не найдена"):
            await self.repository.mark_ready(
                workspace_id=second,
                media_id=first_media,
                provider="cloud-pro",
                model="pro-model",
                report=cast(dict[str, Any], _quality_report()),
            )
        async with self.database.acquire() as connection:
            untouched = await connection.fetchrow(
                """
                SELECT status, provider, model
                FROM workspace_qwen_checks
                WHERE workspace_id = $1::BIGINT AND media_id = $2::BIGINT
                """,
                second,
                second_media,
            )
        self.assertEqual(("pending", None, None), tuple(untouched))


if __name__ == "__main__":
    unittest.main()
