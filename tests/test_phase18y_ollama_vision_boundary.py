from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from velvet_bot.ai_vision import MediaAIRepository, VisionAnalysisTarget
from velvet_bot.ollama_vision import ReliableMediaAIRepository


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        self.exited = True
        return False


class OllamaVisionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(ReliableMediaAIRepository)

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 2)

    async def test_claim_preserves_requeue_and_response_version_update(self) -> None:
        first_connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        second_connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        first_context = _AsyncContext(first_connection)
        second_context = _AsyncContext(second_connection)
        database = SimpleNamespace(
            acquire=Mock(side_effect=[first_context, second_context])
        )
        repository = ReliableMediaAIRepository(database)
        target = VisionAnalysisTarget(
            media_id=41,
            telegram_file_id="file",
            preview_file_id=None,
            mime_type="image/jpeg",
        )

        with patch.object(
            MediaAIRepository,
            "claim_targets",
            new=AsyncMock(return_value=(target,)),
        ) as parent_claim:
            result = await repository.claim_targets(
                provider="ollama",
                model="qwen",
                max_attempts=3,
                limit=1,
            )

        self.assertEqual(database.acquire.call_count, 2)
        self.assertTrue(first_context.entered)
        self.assertTrue(first_context.exited)
        self.assertTrue(second_context.entered)
        self.assertTrue(second_context.exited)
        requeue_sql, response_version = first_connection.execute.await_args.args
        self.assertIn("analysis_version <", requeue_sql)
        self.assertIn("status IN ('error', 'skipped')", requeue_sql)
        self.assertEqual(response_version, 2)
        parent_claim.assert_awaited_once_with(
            provider="ollama",
            model="qwen",
            max_attempts=3,
            limit=1,
        )
        version_sql, media_ids, response_version = second_connection.execute.await_args.args
        self.assertIn("SET analysis_version", version_sql)
        self.assertEqual(media_ids, [41])
        self.assertEqual(response_version, 2)
        self.assertEqual(result, (target,))

    async def test_empty_claim_skips_second_database_acquire(self) -> None:
        connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 0"))
        context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=context))
        repository = ReliableMediaAIRepository(database)

        with patch.object(
            MediaAIRepository,
            "claim_targets",
            new=AsyncMock(return_value=()),
        ):
            result = await repository.claim_targets(
                provider="ollama",
                model="qwen",
                max_attempts=3,
            )

        database.acquire.assert_called_once_with()
        self.assertEqual(result, ())


if __name__ == "__main__":
    unittest.main()
