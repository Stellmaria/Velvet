from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from velvet_bot.ai_quality import AIQualityRepository
from velvet_bot.ai_vision import VisionAnalysisTarget
from velvet_bot.resilient_ai_quality import ResilientAIQualityRepository


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


class ResilientAIQualityRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_oversized_skipped_check_is_requeued_once(self) -> None:
        first_connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        second_connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        database = SimpleNamespace(
            acquire=Mock(
                side_effect=[
                    _AsyncContext(first_connection),
                    _AsyncContext(second_connection),
                ]
            )
        )
        repository = ResilientAIQualityRepository(database)
        target = VisionAnalysisTarget(
            media_id=2618,
            telegram_file_id="large-file-id",
            preview_file_id=None,
            mime_type="image/png",
        )

        with patch.object(
            AIQualityRepository,
            "claim_targets",
            new=AsyncMock(return_value=(target,)),
        ) as parent_claim:
            result = await repository.claim_targets(
                provider="ollama",
                model="qwen3-vl:8b",
                max_attempts=3,
                limit=1,
            )

        requeue_sql, response_version = first_connection.execute.await_args.args
        self.assertIn("file is too big", requeue_sql)
        self.assertEqual(2, response_version)
        parent_claim.assert_awaited_once_with(
            provider="ollama",
            model="qwen3-vl:8b",
            max_attempts=3,
            limit=1,
        )
        version_sql, media_ids, response_version = second_connection.execute.await_args.args
        self.assertIn("SET analysis_version", version_sql)
        self.assertEqual([2618], media_ids)
        self.assertEqual(2, response_version)
        self.assertEqual((target,), result)


if __name__ == "__main__":
    unittest.main()
