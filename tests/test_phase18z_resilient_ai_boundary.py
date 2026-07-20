from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from velvet_bot.ai_vision import VisionAnalysisTarget
from velvet_bot.ollama_vision import ReliableMediaAIRepository
from velvet_bot.resilient_ai_vision import (
    ResilientMediaAIRepository,
    ResilientMediaAIVisionService,
)


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


class ResilientAIBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(ResilientMediaAIRepository)

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 3)
        self.assertNotIn(
            "_database.acquire",
            inspect.getsource(ResilientMediaAIVisionService),
        )

    async def test_claim_preserves_transient_requeue_and_version_update(self) -> None:
        first_connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        second_connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        first_context = _AsyncContext(first_connection)
        second_context = _AsyncContext(second_connection)
        database = SimpleNamespace(
            acquire=Mock(side_effect=[first_context, second_context])
        )
        repository = ResilientMediaAIRepository(database)
        target = VisionAnalysisTarget(
            media_id=51,
            telegram_file_id="file",
            preview_file_id="preview",
            mime_type="image/jpeg",
        )

        with patch.object(
            ReliableMediaAIRepository,
            "claim_targets",
            new=AsyncMock(return_value=(target,)),
        ) as parent_claim:
            result = await repository.claim_targets(
                provider="ollama",
                model="qwen",
                max_attempts=4,
                limit=2,
            )

        self.assertEqual(database.acquire.call_count, 2)
        requeue_sql, response_version = first_connection.execute.await_args.args
        self.assertIn("ServerDisconnectedError", requeue_sql)
        self.assertIn("TelegramNetworkError", requeue_sql)
        self.assertIn("file is too big", requeue_sql)
        self.assertEqual(response_version, 4)
        parent_claim.assert_awaited_once_with(
            provider="ollama",
            model="qwen",
            max_attempts=4,
            limit=2,
        )
        version_sql, media_ids, response_version = second_connection.execute.await_args.args
        self.assertIn("SET analysis_version", version_sql)
        self.assertEqual(media_ids, [51])
        self.assertEqual(response_version, 4)
        self.assertEqual(result, (target,))

    async def test_empty_claim_skips_second_database_acquire(self) -> None:
        connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 0"))
        database = SimpleNamespace(
            acquire=Mock(return_value=_AsyncContext(connection))
        )
        repository = ResilientMediaAIRepository(database)

        with patch.object(
            ReliableMediaAIRepository,
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
