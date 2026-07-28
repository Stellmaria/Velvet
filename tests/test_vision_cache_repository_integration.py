from __future__ import annotations

import os
import unittest
from decimal import Decimal

from velvet_bot.database import Database
from velvet_bot.domains.vision_routing import (
    VisionAnalysisCacheRepository,
    VisionCascadeResult,
    VisionRoute,
)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class VisionCacheRepositoryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database.acquire() as connection:
            await connection.execute("TRUNCATE ai_vision_cache RESTART IDENTITY")
        self.repository = VisionAnalysisCacheRepository(self.database)

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_store_find_and_increment_hit_count(self) -> None:
        result = VisionCascadeResult(
            profile={
                "series_title_ru": "Дикий Запад",
                "summary_ru": "Пустынная сцена.",
                "confidence": 88,
            },
            content_hash="a" * 64,
            route=VisionRoute.PRO,
            provider="test-provider",
            model="pro-model",
            confidence=88,
            cache_hit=False,
            attempts=(VisionRoute.FLASH, VisionRoute.PRO),
            input_tokens=1200,
            output_tokens=300,
            actual_cost_rub=Decimal("1.2500"),
        )
        await self.repository.store(
            result,
            analysis_type="semantic-profile",
            prompt_version=3,
            input_tokens=1200,
            output_tokens=300,
            actual_cost_rub=Decimal("1.2500"),
        )

        cached = await self.repository.find(
            content_hash="a" * 64,
            analysis_type="semantic-profile",
            prompt_version=3,
            models=("flash-model", "pro-model"),
        )

        self.assertIsNotNone(cached)
        assert cached is not None
        self.assertEqual(VisionRoute.PRO, cached.route)
        self.assertEqual("pro-model", cached.model)
        self.assertEqual(88, cached.confidence)
        self.assertEqual(Decimal("1.2500"), cached.actual_cost_rub)
        stats = await self.repository.stats()
        self.assertEqual(1, stats["entries"])
        self.assertEqual(1, stats["hits"])

    async def test_model_and_prompt_version_are_part_of_cache_key(self) -> None:
        result = VisionCascadeResult(
            profile={"confidence": 75},
            content_hash="b" * 64,
            route=VisionRoute.FLASH,
            provider="test-provider",
            model="flash-v1",
            confidence=75,
            cache_hit=False,
        )
        await self.repository.store(
            result,
            analysis_type="semantic-profile",
            prompt_version=1,
        )

        wrong_model = await self.repository.find(
            content_hash="b" * 64,
            analysis_type="semantic-profile",
            prompt_version=1,
            models=("flash-v2",),
        )
        wrong_prompt = await self.repository.find(
            content_hash="b" * 64,
            analysis_type="semantic-profile",
            prompt_version=2,
            models=("flash-v1",),
        )
        self.assertIsNone(wrong_model)
        self.assertIsNone(wrong_prompt)


if __name__ == "__main__":
    unittest.main()
